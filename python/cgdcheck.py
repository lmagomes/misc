import configparser
import os
import sys
import time
from datetime import date, timedelta

import pandas as pd
import pynma
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

    if curr_funds > yest_funds:
        title = "Funds up!"
        message = "Funds went up from {0:.2f} to {1:.2f}.\n{2}".format(
            yest_funds,
            curr_funds,
            funds[funds.date >= date.today() - timedelta(days=1)][['type', 'date', 'value']].to_string(index=False)
        )
    elif curr_funds < yest_funds:
        title = "Funds down!"
        message = "Funds went down from {0:.2f} to {1:.2f}.\n{2}".format(
            yest_funds,
            curr_funds,
            funds[funds.date >= date.today() - timedelta(days=1)][['type', 'date', 'value']].to_string(index=False)
        )
    else:
        # no change. Probably a weekend or holiday
        title = "No change!"
        message = "Funds remained at {0:.2f}.\n{1}".format(
            curr_funds,
            funds[funds.date >= date.today() - timedelta(days=1)][['type', 'date', 'value']].to_string(index=False)
        )

    nma = pynma.PyNMA(config['pynma']['key'])
    res = nma.push('CGD Funds', title, message)

