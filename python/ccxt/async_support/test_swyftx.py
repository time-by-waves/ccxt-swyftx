import ccxt.async_support as ccxt
import asyncio
import logging
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_swyftx():
    exchange = ccxt.swyftx({
        'apiKey': os.getenv('SWYFTX_API_KEY'),
        'secret': os.getenv('SWYFTX_API_SECRET'),
        'enableRateLimit': True
    })
    exchange.verbose = True
    symbol = 'BTC/AUD'

    try:
        await exchange.load_markets()
        market = exchange.market(symbol)

        # Test authentication
        await exchange.authenticate()
        logger.info(f"Access Token: {exchange.access_token}")

        # Test ticker
        ticker = await exchange.fetch_ticker(symbol)
        logger.info(f"Ticker for {symbol}: {ticker}")

        # Test balance
        balance = await exchange.fetch_balance()
        logger.info(f"Balance: {balance}")

        # Test order creation (sandbox mode)
        exchange.set_sandbox_mode(True)
        amount = 0.001
        order = await exchange.create_order(symbol, 'market', 'buy', amount)
        logger.info(f"Buy Order: {order}")

        # Test order fetching
        order_details = await exchange.fetch_order(order['id'], symbol)
        logger.info(f"Order Details: {order_details}")

        # Test order cancellation
        cancel_result = await exchange.cancel_order(order['id'], symbol)
        logger.info(f"Cancel Order: {cancel_result}")
    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        await exchange.close()

if __name__ == '__main__':
    asyncio.run(test_swyftx())