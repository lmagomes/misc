
# standard python imports
import io
import os
from datetime import datetime
import time
import configparser

# blockchain info for BTC
from blockchain import blockexplorer

# blockchain info for BTC and LTC
import blockcypher

# etherscan for ETH
from etherscan.accounts import Account
from  etherscan.tokens import Tokens

# coinmarketcap for prices
from coinmarketcap import Market

# bittrex API
from bittrex.bittrex import Bittrex, API_V2_0

# bitfinex
from bitex import Bitfinex

# uphold
from uphold import Uphold

# coinbase
from coinbase.wallet.client import Client

# binance
from binance.client import Client as BinClient

# for calculating and storing values
import pandas as pd
from sqlalchemy import create_engine


def get_balance(wallet_type, address, contract_address=None, api_key=None):
    """Get the balance of a single wallet."""

    value = 0
    if wallet_type == 'ETH':
        account = Account(address=address, api_key=api_key)
        value += float(account.get_balance()) / 1000000000000000000
    elif wallet_type == 'EOS':
        api = Tokens(contract_address=contract_address, api_key=api_key)
        value += float(api.get_token_balance(address=address)) / 1000000000000000000
    elif wallet_type == 'XRB':
        # hardcoded for now...
        value = 10.179600
    else:
        value += blockcypher.get_total_balance(address, coin_symbol=wallet_type.lower()) / 100000000
    
    return value

def get_bittrex(key, secret):
    """Get balance from bittrex exchange API."""
    
    my_bittrex = Bittrex(key, secret, api_version=API_V2_0)
    balances = my_bittrex.get_balances()
    df = pd.DataFrame([row['Balance'] for row in balances['result']])
    df = df[['Balance', 'Currency']]
    df['source'] = 'bttrex'
    df.columns = ['balance', 'coin', 'source']
    
    return df

def get_bitfinex(key, secret):
    """Get balance from bitfinex exchange API."""
    
    bfnx = Bitfinex(key, secret)
    balance = bfnx.balance()
    df = pd.DataFrame(balance.formatted)
    df = df[['amount', 'currency']]
    df['source'] = 'bitfinex'
    df.columns = ['balance', 'coin', 'source']
    df['coin'] = df.coin.str.upper()
    
    return df

def get_uphold(key, secret):
    """Get balance from uphold exchange API."""
    
    api = Uphold()
    api.auth_basic(key, secret)
    account = api.get_me()
    df = pd.DataFrame([{**{'coin': coin}, **row} for coin, row in account['balances']['currencies'].items()])
    df['source'] = 'uphold'
    df = df[['balance', 'coin', 'source']]
    
    # return df[df.coin != 'EUR']
    return df

def get_coinbase(key, secret):
    """Get balance from coinbase exchange API."""
    
    client = Client(key, secret)
    accounts = client.get_accounts()
    df = pd.DataFrame([row.balance for row in accounts.data])
    df['source'] = 'coinbase'
    df.columns = ['balance', 'coin', 'source']
    data.append(df)

def get_binance(key, secret):
    """Get balance from binance exchange API."""

    client = BinClient(key, secret)
    acct = client.get_account()
    df = pd.DataFrame(acct['balances'])
    df['source'] = 'binance'

    df = df[['free', 'asset', 'source']]
    df.columns = ['balance', 'coin', 'source']

    return df


if __name__ == '__main__':

    # start date
    current_date = datetime.now().replace(second=0, microsecond=0)
    
    # config loading
    config = configparser.ConfigParser()
    config.read(os.path.join(os.path.expanduser('~'), '.config', 'me.ini'))
    
    # prepare database connection
    dburl = config['db']['url']
    engine = create_engine(dburl)
    
    # get coin market cap data
    coinmarketcap = Market()

    # Since data is falling quite a bit, temporarly check if we got
    # it, and if not, increase the limit of records returned.
    contains_data = False
    limit = 125
    while not contains_data:
        markets = coinmarketcap.ticker(limit=limit, convert='EUR')
        mktdf = pd.DataFrame(markets)

        if len(mktdf[mktdf.symbol == 'DATA']) > 0:
            contains_data = True

        limit += 10
    
    mktdf = pd.DataFrame(markets)
    # convert some columns
    nonnumeric = ['cached', 'id', 'name', 'symbol']
    for col in [numcol for numcol in mktdf.columns if numcol not in nonnumeric]:
        mktdf[col] = pd.to_numeric(mktdf[col])
    # add a read date and save current values to the database
    mktdf['read_date'] = current_date
    mktdf = mktdf[['read_date'] + list(mktdf.columns[:-1])]
    mktdf.to_sql('cryptomarket', engine, if_exists='append', index=False)
    
    # keep only relevant rows
    mktdf = mktdf[['id', 'price_eur', 'name', 'symbol']]
    mktdf['price_eur'] = pd.to_numeric(mktdf.price_eur)
    mktdf.columns = ['id', 'euro_price', 'name', 'coin']
    
    # get data
    data = []
    
    # read wallets
    df = pd.read_sql('cryptowallets', engine)
    df['balance'] = df.apply(lambda x: get_balance(x['coin'], x['address'], x['contract_address'], config['etherscan']['key']), axis=1)
    df = df.groupby(['coin', 'source']).balance.sum().reset_index()
    data.append(df)

    # and exchanges
    for exchange in ['bittrex', 'bitfinex', 'uphold', 'coinbase', 'binance']:
        key = config[exchange]['key']
        secret = config[exchange]['secret']
        data.append(locals()[f"get_{exchange}"](key, secret))
    
    df = pd.concat(data)
    df['balance'] = pd.to_numeric(df.balance)
    # change some coin symbols.
    df.loc[df.coin == 'IOT', 'coin'] = 'MIOTA'
    df.loc[df.coin == 'DAT', 'coin'] = 'DATA'
    df.loc[df.coin == 'BCC', 'coin'] = 'BCH'
    
    # keep only coins with values.
    df = df[df.balance > 0]
    
    # add a read date
    df['read_date'] = current_date
    # and merge with market data
    df = pd.merge(df, mktdf, how='left')
    # change fiat rows. use uphold euro value
    usd_eur = 0.83
    df.loc[df.coin == 'USD', ['id', 'euro_price', 'name']] = ['USD', usd_eur, 'Dollar']
    df.loc[df.coin == 'EUR', ['id', 'euro_price', 'name']] = ['EUR', 1, 'Euro']
    
    # calculate fiat
    df['fiat'] = df['euro_price'] * df['balance']
    
    # change column order
    df = df[['read_date', 'source', 'coin', 'name', 'balance', 'fiat', 'euro_price']]

    # save to database
    df.to_sql('cryptocurrencies', engine, if_exists='append', index=False)
