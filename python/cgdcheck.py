import configparser
import io
import os
import sys
import time
from datetime import date, timedelta

import pandas as pd
import telegram
from tabulate import tabulate


import matplotlib
matplotlib.use('Agg')
import seaborn as sns
sns.set_context("poster")

from pyvirtualdisplay import Display
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from sqlalchemy import create_engine


def get_values(username, password):
    # open headless browser
    """
    Uses selenium and pyvirtualdisplay to go through the necessary steps to get the required values.
    :param username:
    :param password:
    :return:
    """
    display = Display(visible=0, size=(1024, 768))
    display.start()

    browser = webdriver.Firefox()
    browser.set_window_size(1020, 400)
    browser.get('https://www.cgd.pt')

    time.sleep(3)
    # username
    elem = browser.find_element_by_id('input_cx1')
    elem.send_keys(username + Keys.ENTER)
    time.sleep(3)

    # Warning OK
    elem = browser.find_element_by_id('j_id36')
    elem.send_keys(Keys.ENTER)
    time.sleep(3)

    # Set password
    elem = browser.find_element_by_id('passwordInput')
    elem.send_keys(password + Keys.ENTER)
    time.sleep(3)

    # Clear warning
    elem = browser.find_element_by_class_name('botao_ok')
    elem.send_keys(Keys.ENTER)

    # open investing menu
    elem = browser.find_element_by_id('menuLink101150012')
    elem.send_keys(Keys.ENTER)
    time.sleep(3)

    # open fundos menu
    elem = browser.find_element_by_id('menuLink101150012101150032')
    elem.send_keys(Keys.ENTER)
    time.sleep(3)

    # click 
    elem = browser.find_element_by_link_text('Carteira e movimentos')
    elem.send_keys(Keys.ENTER)
    time.sleep(3)

    # get wanted data
    elem = browser.find_element_by_id('tbMercado_PT')

    values = elem.text

    # close browser
    browser.close()
    display.stop()

    return values


def convert_df(values):
    """
    Converts a string with the lines to a pandas data frame.
    :param values: a multiline string
    :return: a pandas data frame.
    """
    funds = []
    for val in values.splitlines():
        if 'CXG' in val:
            fields = val.replace('»', '').replace('.', '').replace(',', '.').rsplit(' ', 4)

            funds.append({
                'type': fields[0],
                'date': date.today(),
                'available': fields[1],
                'liquidated': fields[2],
                'closing': fields[3],
                'value': fields[4],
            })

    return pd.DataFrame(funds)


if __name__ == '__main__':

    # get needed values from config
    config = configparser.ConfigParser()
    config.read(os.path.join(os.path.expanduser("~"), '.config', 'me.ini'))

    engine = create_engine(config['db']['url'])
    old_funds = pd.read_sql('cgd_funds', engine)
    todays_values = old_funds[old_funds.date == date.today()]
    
    if len(todays_values) != 0:
        print("Already looked up today's values!")
        sys.exit(0)

    # get new funds
    new_funds = convert_df(get_values(config['cgd']['username'], config['cgd']['password']))
    funds = pd.concat([old_funds, new_funds])
    funds.value = pd.to_numeric(funds.value)
    funds.date = pd.to_datetime(funds.date)

    new_funds.to_sql('cgd_funds', engine, if_exists='append', index=False)

    curr_funds = funds[funds.date == date.today()].value.sum()
    yest_funds = funds[funds.date == date.today() - timedelta(days=1)].value.sum()
    
    df = funds[funds.date >= date.today() - timedelta(days=1)].copy()
    df.date = df.date.apply(lambda x: x.date().strftime('%y-%m-%d'))
    df = df[['date', 'value', 'type']].pivot(columns='date', index='type', values='value')
    df.index = df.index.str[:7]


    if curr_funds > yest_funds:
        message = "Funds went up from {0:.2f} € to {1:.2f} €.\n\n{2}".format(
            yest_funds,
            curr_funds,
            tabulate(df, headers=['type'] + list(df.columns))
        )
    elif curr_funds < yest_funds:
        message = "Funds went down from {0:.2f} € to {1:.2f} €.\n\n{2}".format(
            yest_funds,
            curr_funds,
            tabulate(df, headers=['type'] + list(df.columns))
        )
    else:
        # no change. Probably a weekend or holiday
        message = None
        
    
    if message:
        # get invested values
        movements = pd.read_sql('account_movements', engine)
        invested = movements[movements.description == 'Subscrição Fundos'].ammount.sum()
        single_inv = invested / 2
        # get daily values
        funds = funds[['date', 'type', 'value']]
        funds['percentage'] = ((funds.value / single_inv) - 1) * 100
        daily = funds.pivot_table(index='date', columns='type', values=['value', 'percentage'], aggfunc=sum)
        daily_total = funds.pivot_table(index='date', values=['value'], aggfunc=sum)
        daily_total['percentage'] = ((daily_total.value / invested) - 1) * 100
        # create a plot from the daily values
        fig = matplotlib.pyplot.figure()
        ax1 = fig.add_subplot(111)
        ax2 = ax1.twinx()
        daily_total.value.plot(ax=ax1, color='r')
        daily.value.plot(ax=ax2)
        
        buf = io.BytesIO()
        fig.savefig(buf, format='png')
        buf.seek(0)
    
        # send message and image.
        bot = telegram.Bot(token=config['telegram']['token'])
        bot.sendMessage(chat_id=config['telegram']['chat_id'], text=message)
        bot.sendPhoto(chat_id=config['telegram']['chat_id'], photo=io.BufferedReader(buf))
