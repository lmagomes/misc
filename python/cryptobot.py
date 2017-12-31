import io
import os
from datetime import datetime
import time
import configparser
import logging
from functools import lru_cache

from sqlalchemy import create_engine

import pandas as pd
import matplotlib
matplotlib.use('Agg')

import matplotlib.pyplot as plt
plt.style.use('seaborn-poster')

import telegram
from telegram.ext import Updater
from telegram.ext import CommandHandler

from tabulate import tabulate

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

_UNAUTHORIZED_MESSAGE_ = "Hey! You weren't supposed to be here!"

@lru_cache(maxsize=32)
def get_config():
    config = configparser.ConfigParser()
    config.read(os.path.join(os.path.expanduser('~'), '.config', 'me.ini'))
    
    return config

def get_data():
    config = get_config()
    
    dburl = config['db']['url']
    engine = create_engine(dburl)
    
    # read database data
    df = pd.read_sql('''
        select
            cur.*,
            mkt.price_btc,
            mkt.price_eur,
            mkt.percent_change_1h as change
        from cryptomarket mkt right join cryptocurrencies cur on mkt.read_date = cur.read_date and mkt.symbol = cur.coin
    ''', engine)
    
    
    df.loc[df.coin =='EUR', 'price_eur'] = 1
    df.loc[df.coin =='EUR', 'price_btc'] = 1 / df[df.coin == 'BTC'].price_eur.max()

    df['btc_value'] = df.balance * df.price_btc
    df['eur_value'] = df.balance * df.price_eur
    
    return df
    

def check_chat_id(chat_id):
    config = get_config()
    
    logging.info(f'Checking chat id {chat_id}.')
    
    return True if chat_id == int(config['telegram']['chat_id']) else False
    
def get_portfolio_data():
    df = get_data()
    portfolio = df[df.read_date == df.read_date.max()]
    
    return portfolio


def get_coin_pairs(bot, update):
    config = get_config()
    
    dburl = config['db']['url']
    engine = create_engine(dburl)
    
    # read database data
    df = pd.read_sql('''
        select distinct name, coin
        from cryptocurrencies
    ''', engine)
    
    if check_chat_id(update.message.chat_id):
        message = tabulate(df.sort_values(by='name'), headers=list(df.columns), showindex="never")
    else:
        message = _UNAUTHORIZED_MESSAGE_
    
    bot.send_message(chat_id=update.message.chat_id, text=message)


def get_values(bot, update):

    portfolio = get_portfolio_data()
    btc = portfolio.btc_value.sum()
    eur = portfolio.eur_value.sum()
    btc_eur = portfolio[portfolio.name == 'Bitcoin'].price_eur.max()

    if check_chat_id(update.message.chat_id):
        message = f'Total is {eur:.2f} € or {btc} btc. This would be {btc_eur * btc:.2f} € if it was all BTC.'
    else:
        message = _UNAUTHORIZED_MESSAGE_

    bot.send_message(chat_id=update.message.chat_id, text=message)

    
def get_portfolio(bot, update):
    
    portfolio = get_portfolio_data()
    grouped = portfolio.groupby(['name'])['btc_value', 'eur_value', 'change'].sum()
    #grouped = grouped.reset_index().sort_values(by='eur_value', ascending=False)
    grouped = grouped.reset_index().sort_values(by='name')
    
    if check_chat_id(update.message.chat_id):
        headers = ['Coin', 'BTC', 'Euro', '% Change']
        message = tabulate(grouped, headers=headers, showindex="never")
    else:
        message = _UNAUTHORIZED_MESSAGE_
    
    bot.send_message(chat_id=update.message.chat_id, text=message)


def get_valuechart(bot, update, args):
    df = get_data()
    
    coins = []
    columns = []
    delcoins = []
    values = []
    removecoins = False
    for arg in args:
        if arg == '-split':
            columns = ['coin']
        elif arg == '-rem':
            removecoins = True
        elif arg == '-eur':
            values = ['eur_value']
        elif arg == '-btc':
            values = ['btc_value']
        elif removecoins:
            delcoins.append(arg.upper())
        else:
            coins.append(arg.upper())
    
    if len(coins) > 0:
        df = df[df.coin.isin(coins)]
    if len(delcoins) > 0:
        df = df[~df.coin.isin(delcoins)]
    
    # create a new figure
    fig = plt.figure()
    if not values:
        ax1 = fig.add_subplot(111)
        ax2 = ax1.twinx()

        df.pivot_table(index='read_date', values=['btc_value'], columns=columns, aggfunc=sum).plot(ax=ax1, color='r')
        df.pivot_table(index='read_date', values=['eur_value'], columns=columns, aggfunc=sum).plot(ax=ax2)

    else:
        ax1 = fig.add_subplot(111)
        df.pivot_table(index='read_date', values=values, columns=columns, aggfunc=sum).plot(ax=ax1)
    
    # write image data to a buffer
    buf = io.BytesIO()
    fig.savefig(buf, format='png')
    buf.seek(0)
    
    if check_chat_id(update.message.chat_id):
        bot.sendPhoto(chat_id=update.message.chat_id, photo=io.BufferedReader(buf))
    else:
        bot.send_message(chat_id=update.message.chat_id, text=_UNAUTHORIZED_MESSAGE_)
    
if __name__ == '__main__':
    
    """
    bot father commands
    
    /setcommands
    
    @botname
    
    coins - Get coin pairs
    c - Get coin pairs
    values - Get current database values
    v - Get current database values
    portfolio - Get current portfolio table
    p - Get current portfolio table
    valuechart - Get values over time
    vc - Get values over time
    """
    
    config = get_config()
    
    updater = Updater(token=config['telegram']['token'])
    dispatcher = updater.dispatcher
    
    coinshandler = CommandHandler('coins', get_coin_pairs)
    dispatcher.add_handler(coinshandler)
    coinshandler = CommandHandler('c', get_coin_pairs)
    dispatcher.add_handler(coinshandler)
    
    valueshandler = CommandHandler('values', get_values)
    dispatcher.add_handler(valueshandler)
    valueshandler = CommandHandler('v', get_values)
    dispatcher.add_handler(valueshandler)
    
    portfoliohandler = CommandHandler('portfolio', get_portfolio)
    dispatcher.add_handler(portfoliohandler)
    portfoliohandler = CommandHandler('p', get_portfolio)
    dispatcher.add_handler(portfoliohandler)
    
    valuecharthandler = CommandHandler('valuechart', get_valuechart, pass_args=True)
    dispatcher.add_handler(valuecharthandler)
    valuecharthandler = CommandHandler('vc', get_valuechart, pass_args=True)
    dispatcher.add_handler(valuecharthandler)
    
    logging.info('Starting.')
    updater.start_polling()
    