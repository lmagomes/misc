import configparser
import os
import time

import pandas as pd
import pynma
import requests
import tabulate
from bs4 import BeautifulSoup
from sqlalchemy import create_engine


def check_ctt(order_number):
    payload = {'showResults': 'true', 'objects': order_number}
    r = requests.post("http://www.ctt.pt/feapl_2/app/open/objectSearch/objectSearch.jspx?lang=01", data=payload)

    ctt_data = BeautifulSoup(r.text, 'html5lib')
    data_table = ctt_data.findAll('table')[1]

    data = []
    last_date = None
    for tr in data_table.findAll('tr'):
        tds = tr.findAll('td')

        if len(tds) == 1:
            last_date = tds[0].text
        elif len(tds) > 1:
            data.append({
                'date': '{} {}'.format(last_date, tds[0].text),
                'location': tds[3].text,
                'details': ' '.join([x for x in [tds[2].text, tds[4].text, tds[1].text] if x != '-'])
            })

    df = pd.DataFrame(data)[['date', 'location', 'details']]

    return df


def check_flytexpress(order_number):
    r = requests.get('http://flytexpress.com/Tracking/NewTracking_En.aspx?trackNumber=' + order_number)
    page = BeautifulSoup(r.content, 'lxml')

    lines = []
    for el in page.findAll('table')[2].findAll('tr')[2:]:
        line = ','.join([x.strip() for x in el.findAll(text=True)])
        line = line.replace(',,', ',')
        line = line[1:-1]
        lines.append(line.split(','))

    df = pd.DataFrame(lines)
    df.columns = ['date', 'location', 'details']

    return df


def check_dhl(order_number):
    # DHL

    r = requests.get('http://www.dhl.com/cgi-bin/tracking.pl?AWB=' + order_number)
    page = BeautifulSoup(r.content, 'lxml')
    html = page.findAll('table')[1]

    for tag in html.findAll('hr'):
        tag.extract()

    for tag in html.findAll('td', {"width": "10"}):
        tag.extract()

    for tag in html.findAll('td', {"colspan": "7"}):
        tag.extract()

    for tag in html.findAll('tr'):
        if not tag.text:
            tag.extract()

    for tag in html.findAll('th'):
        if not tag.text:
            tag.extract()

    pd.set_option('display.max_colwidth', -1)
    df = pd.read_html(str(html).replace('<tr>\n</tr>', '').replace('<tr>\n\n</tr>', ''), header=0)[0]

    # transform it a bit
    df['date'] = df['Date'] + ' ' + df['Time']
    df = df[['date', 'Location Service Area', 'Checkpoint Details']]
    df.columns = ['date', 'location', 'details']

    return df


def check_mrw(order_number):
    r = requests.get('http://www.mrw.pt/seguimiento_envios/MRW_historico_nacional.asp?enviament=' + order_number)
    page = BeautifulSoup(r.content, 'html5lib')
    table = page.findAll('table')[0]

    df = pd.read_html(str(table), header=0)[0]

    # transform it a bit
    df['date'] = df['Data'] + ' ' + df['Hora']
    df = df[['date', 'Localização', 'Estado envio']]
    df.columns = ['date', 'location', 'details']

    return df


if __name__ == '__main__':

    # get needed values from config
    config = configparser.ConfigParser()
    config.read(os.path.join(os.path.expanduser("~"), '.config', 'me.ini'))

    engine = create_engine(config['db']['url'])
    packages = pd.read_sql('packages', engine)
    package_details = pd.read_sql('package_details', engine)

    nma = pynma.PyNMA(config['pynma']['key'])

    # current package checkers
    packagecheck = {
        'ctt': check_ctt,
        'flytexpress': check_flytexpress,
        'dhl': check_dhl,
        'mrw': check_mrw,
    }

    for index, row in packages[packages.delivered == False].iterrows():
        data = packagecheck[row.carrier](row.code)
        data['date'] = pd.to_datetime(data['date'])
        data['package_id'] = row.package_id
        data.sort_values(by='date', ascending=False, inplace=True)

        old_data = package_details[package_details.package_id == row.package_id]

        diff = len(data) - len(old_data)
        if diff > 0:
            new_data = data[:diff]
            new_data.to_sql('package_details', engine, if_exists='append', index=False)

            nma.push('Packages', '{} {}'.format(row.description, row.code), tabulate.tabulate(data, tablefmt='grid'))

        time.sleep(1)

