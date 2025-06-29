from ccxt.async_support.base.exchange import Exchange
import hashlib
import json
from typing import Optional, List, Dict, Any
from ccxt.base.errors import ExchangeError, AuthenticationError, InsufficientFunds, InvalidOrder, OrderNotFound, BadRequest, RateLimitExceeded, NotSupported
from ccxt.base.types import Order, Balances, Market, Ticker, Tickers, OHLCV
from ccxt.base.decimal_to_precision import TICK_SIZE

class swyftx(Exchange):
    def __init__(self, config={}):
        super().__init__()
        self.access_token = None
        self.api = {
            'public': {
                'get': [
                    'markets/info/basic/{assetCode}',
                    'markets/info/detail/{assetCode}',
                    'markets/assets',
                    'charts/v2/getBars/{baseAsset}/{secondaryAsset}/{side}',
                    'charts/listBars',
                    'charts/getBars',
                    'charts/resolveSymbol',
                    'assets',
                    'enabled-assets',
                    'live-rates/{assetId}',
                    'orders/{marketId}',
                    'orders/{primaryAsset}/{secondaryAsset}',
                    'trades/{marketId}',
                    'history/{assetId}',
                ],
                'post': ['auth/refresh/'],
            },
            'private': {
                'get': [
                    'user/balance',
                    'user/statistics/accountValue',
                    'orders',
                    'orders/byId/{orderUuid}',
                    'orders/detail/{orderId}',
                    'limits/withdrawal',
                    'trade/details/{tradeUuid}',
                    'history',
                ],
                'post': ['orders', 'orders/market', 'withdraw', 'transfer'],
                'delete': ['orders/{orderId}'],
                'put': ['orders/{orderUuid}'],
            },
        }
        self.urls = {
            'api': {
                'public': 'https://api.swyftx.com.au',
                'private': 'https://api.swyftx.com.au',
            },
            'www': 'https://swyftx.com',
            'doc': 'https://docs.swyftx.com.au',
            'fees': 'https://swyftx.com/au/fees/',
            'referral': 'https://trade.swyftx.com.au/register/?ref=simonvictory',
        }
        self.options = {
            'assetsByCode': None,
            'assetsById': None,
        }
        self.fees = {
            'trading': {
                'tierBased': True,
                'percentage': True,
                'taker': self.parse_number('0.006'),  # 0.6%
                'maker': self.parse_number('0.006'),  # 0.6%
            },
            'funding': {'withdraw': {}, 'deposit': {}},
        }
        self.exceptions = {
            'exact': {
                'Invalid API Key': AuthenticationError,
                'Invalid signature': AuthenticationError,
                'Invalid nonce': AuthenticationError,
                'Invalid authentication credentials': AuthenticationError,
                'Insufficient funds': InsufficientFunds,
                'Insufficient balance': InsufficientFunds,
                'Invalid order': InvalidOrder,
                'Order not found': OrderNotFound,
                'Market not found': BadRequest,
                'Asset not found': BadRequest,
                'Rate limit exceeded': RateLimitExceeded,
                'Trading is disabled': NotSupported,
            },
            'broad': {
                'API key': AuthenticationError,
                'signature': AuthenticationError,
                'authentication': AuthenticationError,
                'Unauthorized': AuthenticationError,
                'funds': InsufficientFunds,
                'balance': InsufficientFunds,
                'Invalid': InvalidOrder,
                'Not found': OrderNotFound,
                'Rate limit': RateLimitExceeded,
                'disabled': NotSupported,
            },
        }
        self.precision_mode = TICK_SIZE
        self.update_config(config)

    async def fetch_markets(self, params={}) -> List[Market]:
        assets_url = f"{self.urls['api']['public']}/markets/assets/"
        assets_response = await self.fetch(assets_url)
        assets_by_id = self.index_by(assets_response, 'id')
        result = []
        aud_id = '1'
        aud_asset = assets_by_id.get(aud_id)
        if not aud_asset:
            raise ExchangeError(f"{self.id} fetchMarkets() could not find AUD asset")
        live_rates_url = f"{self.urls['api']['public']}/live-rates/{aud_id}/"
        live_rates_response = await self.fetch(live_rates_url)
        quote_code = self.safe_currency_code(aud_asset.get('code'))
        price_scale = self.safe_integer(aud_asset, 'price_scale', 6)
        price_precision = 10 ** (-price_scale)
        for base_id in live_rates_response.keys():
            if base_id == aud_id:
                continue
            base_asset = assets_by_id.get(base_id)
            if not base_asset:
                continue
            rate_info = live_rates_response[base_id]
            base = self.safe_currency_code(base_asset.get('code'))
            symbol = f"{base}/{quote_code}"
            base_minimum = self.safe_number(base_asset, 'minimum_order')
            base_min_increment = self.safe_number(base_asset, 'minimum_order_increment')
            base_price_scale = self.safe_integer(base_asset, 'price_scale', 8)
            amount_precision = base_min_increment or (10 ** (-base_price_scale))
            buy_liquidity_flag = self.safe_value(rate_info, 'buyLiquidityFlag', False)
            sell_liquidity_flag = self.safe_value(rate_info, 'sellLiquidityFlag', False)
            deposit_enabled = self.safe_value(base_asset, 'deposit_enabled', True)
            withdraw_enabled = self.safe_value(base_asset, 'withdraw_enabled', True)
            active = not buy_liquidity_flag and not sell_liquidity_flag and deposit_enabled and withdraw_enabled
            result.append({
                'id': f"{base_id}/{aud_id}",
                'symbol': symbol,
                'base': base,
                'quote': quote_code,
                'settle': None,
                'baseId': base_id,
                'quoteId': aud_id,
                'settleId': None,
                'type': 'spot',
                'spot': True,
                'margin': False,
                'swap': False,
                'future': False,
                'option': False,
                'active': active,
                'contract': False,
                'linear': None,
                'inverse': None,
                'contractSize': None,
                'expiry': None,
                'expiryDatetime': None,
                'strike': None,
                'optionType': None,
                'precision': {'amount': amount_precision, 'price': price_precision},
                'limits': {
                    'leverage': {'min': None, 'max': None},
                    'amount': {'min': base_minimum, 'max': None},
                    'price': {'min': None, 'max': None},
                    'cost': {'min': None, 'max': None},
                },
                'created': None,
                'info': {'asset': base_asset, 'rate': rate_info},
            })
        return result

    async def fetch_currencies(self, params={}) -> Dict:
        url = f"{self.urls['api']['public']}/markets/assets/"
        response = await self.fetch(url)
        result = {}
        for currency in response:
            id = self.safe_string(currency, 'id')
            code = self.safe_currency_code(self.safe_string(currency, 'code'))
            name = self.safe_string(currency, 'name')
            deposit_enabled = self.safe_value(currency, 'deposit_enabled', True)
            withdraw_enabled = self.safe_value(currency, 'withdraw_enabled', True)
            active = deposit_enabled or withdraw_enabled
            mining_fee = self.safe_number(currency, 'mining_fee')
            price_scale = self.safe_integer(currency, 'price_scale', 8)
            precision = 10 ** (-price_scale)
            min_withdrawal = self.safe_number(currency, 'min_withdrawal')
            minimum_order = self.safe_number(currency, 'minimum_order')
            result[code] = {
                'id': id,
                'code': code,
                'name': name,
                'active': active,
                'deposit': deposit_enabled,
                'withdraw': withdraw_enabled,
                'fee': mining_fee,
                'precision': precision,
                'limits': {
                    'withdraw': {'min': min_withdrawal, 'max': None},
                    'amount': {'min': minimum_order, 'max': None},
                },
                'networks': {},
                'info': currency,
            }
        return result

    async def load_asset_mapping(self):
        if self.options['assetsByCode'] is not None:
            return
        url = f"{self.urls['api']['public']}/markets/assets/"
        assets = await self.fetch(url)
        assets_by_code = {}
        assets_by_id = {}
        for asset in assets:
            code = self.safe_string(asset, 'code')
            id = self.safe_string(asset, 'id')
            assets_by_code[code] = asset
            assets_by_id[id] = asset
        self.options['assetsByCode'] = assets_by_code
        self.options['assetsById'] = assets_by_id

    async def authenticate(self):
        path = 'auth/refresh/'
        request = {'apiKey': self.api_key}
        response = await self.fetch(f"{self.urls['api']['public']}/{path}", 'POST', {'Content-Type': 'application/json'}, json.dumps(request))
        self.access_token = self.safe_string(response, 'accessToken')
        return response

    async def fetch_balance(self, params={}) -> Balances:
        await self.load_markets()
        await self.load_asset_mapping()
        path = 'user/balance/'
        signed = self.sign(path, 'private', 'GET', params)
        response = await self.fetch(signed['url'], signed['method'], signed['headers'], signed['body'])
        return self.parse_balance(response)

    def parse_balance(self, response) -> Balances:
        result = {'info': response}
        assets_by_id = self.safe_value(self.options, 'assetsById', {})
        for balance in response:
            asset_id = self.safe_string(balance, 'assetId')
            available_balance = self.safe_string(balance, 'availableBalance')
            code = asset_id
            asset = assets_by_id.get(asset_id)
            if asset:
                code = self.safe_currency_code(self.safe_string(asset, 'code'))
            else:
                market_id = f"{asset_id}/1"
                market = self.safe_value(self.markets_by_id, market_id)
                if market:
                    code = market['base']
            account = self.account()
            account['free'] = available_balance
            account['total'] = available_balance
            result[code] = account
        return self.safe_balance(result)

    async def create_order(self, symbol: str, type: str, side: str, amount: float, price: Optional[float] = None, params={}) -> Order:
        await self.load_markets()
        market = self.market(symbol)
        order_type = None
        if type == 'market':
            order_type = '3' if side == 'buy' else '4'
        elif type == 'limit':
            order_type = '1' if side == 'buy' else '2'
        else:
            raise InvalidOrder(f"{self.id} create_order() does not support order type {type}")
        primary = market['base']
        secondary = market['quote']
        quantity = self.amount_to_precision(symbol, amount)
        asset_quantity = market['base']
        trigger = None
        if type == 'limit' and price is not None:
            if side == 'buy':
                trigger = self.price_to_precision(symbol, price)
                primary = market['quote']
                secondary = market['base']
                quantity = self.cost_to_precision(symbol, amount * price)
                asset_quantity = market['quote']
            else:
                trigger = self.number_to_string(1 / price)
                quantity = self.amount_to_precision(symbol, amount)
                asset_quantity = market['base']
        request = {
            'primary': primary,
            'secondary': secondary,
            'quantity': quantity,
            'assetQuantity': asset_quantity,
            'orderType': order_type,
        }
        if trigger:
            request['trigger'] = trigger
        path = 'orders'
        signed = self.sign(path, 'private', 'POST', {**request, **params})
        response = await self.fetch(signed['url'], signed['method'], signed['headers'], signed['body'])
        order = self.safe_value(response, 'order', {})
        return self.parse_order({**order, 'orderUuid': self.safe_string(response, 'orderUuid')}, market)

    async def cancel_order(self, id: str, symbol: Optional[str] = None, params={}) -> Order:
        await self.load_markets()
        path = f"orders/{id}/"
        signed = self.sign(path, 'private', 'DELETE', {'orderUuid': id})
        response = await self.fetch(signed['url'], signed['method'], signed['headers'], signed['body'])
        return {
            'id': id,
            'clientOrderId': None,
            'info': response,
            'status': 'canceled',
            'symbol': symbol,
            'type': None,
            'side': None,
            'price': None,
            'amount': None,
            'filled': None,
            'remaining': None,
            'timestamp': None,
            'datetime': None,
            'fee': None,
            'trades': None,
        }

    async def fetch_order(self, id: str, symbol: Optional[str] = None, params={}) -> Order:
        await self.load_markets()
        await self.load_asset_mapping()
        path = f"orders/byId/{id}"
        signed = self.sign(path, 'private', 'GET')
        response = await self.fetch(signed['url'], signed['method'], signed['headers'], signed['body'])
        return self.parse_order(response)

    async def fetch_orders(self, symbol: Optional[str] = None, since: Optional[int] = None, limit: Optional[int] = None, params={}) -> List[Order]:
        await self.load_markets()
        path = 'orders/'
        market = None
        if symbol:
            market = self.market(symbol)
            path += f"{market['base']}/"
        query = {}
        if limit:
            query['limit'] = limit
        if 'page' in params:
            query['page'] = params.pop('page')
        signed = self.sign(path, 'private', 'GET', {**query, **params})
        response = await self.fetch(signed['url'], signed['method'], signed['headers'], signed['body'])
        return self.parse_orders(response, market, since, limit)

    async def fetch_open_orders(self, symbol: Optional[str] = None, since: Optional[int] = None, limit: Optional[int] = None, params={}) -> List[Order]:
        orders = await self.fetch_orders(symbol, since, limit, params)
        return [order for order in orders if order['status'] == 'open']

    async def fetch_closed_orders(self, symbol: Optional[str] = None, since: Optional[int] = None, limit: Optional[int] = None, params={}) -> List[Order]:
        orders = await self.fetch_orders(symbol, since, limit, params)
        return [order for order in orders if order['status'] in ['closed', 'canceled', 'failed']]

    async def edit_order(self, id: str, symbol: str, type: str, side: str, amount: Optional[float] = None, price: Optional[float] = None, params={}) -> Order:
        await self.load_markets()
        market = self.market(symbol)
        if type != 'limit':
            raise NotSupported(f"{self.id} edit_order() only supports limit orders")
        if price is None and amount is None:
            raise InvalidOrder(f"{self.id} edit_order() requires price and/or amount")
        request_params = {'orderUuid': id}
        if price is not None:
            request_params['trigger'] = self.price_to_precision(symbol, price)
        if amount is not None:
            request_params['quantity'] = self.amount_to_precision(symbol, amount)
            request_params['assetQuantity'] = market['base']
        path = 'orders/{orderUuid}'
        signed = self.sign(path, 'private', 'PUT', {**request_params, **params})
        response = await self.fetch(signed['url'], signed['method'], signed['headers'], signed['body'])
        updated_order_uuid = self.safe_string(response, 'orderUuid')
        if not updated_order_uuid:
            raise ExchangeError(f"{self.id} edit_order() failed to update order. Response: {json.dumps(response)}")
        return await self.fetch_order(updated_order_uuid, symbol)

    async def fetch_ticker(self, symbol: str, params={}) -> Ticker:
        await self.load_markets()
        market = self.market(symbol)
        url = f"{self.urls['api']['public']}/live-rates/{market['quoteId']}/"
        response = await self.fetch(url)
        rate_info = self.safe_value(response, market['baseId'])
        if not rate_info:
            raise BadRequest(f"{self.id} fetch_ticker() symbol {symbol} not found")
        detail_url = f"{self.urls['api']['public']}/markets/info/detail/{market['base']}/"
        detail_info = {}
        try:
            detail_info = await self.fetch(detail_url)
        except Exception:
            pass
        return self.parse_ticker({'assetId': market['baseId'], **rate_info, 'detail': detail_info}, market)

    async def fetch_tickers(self, symbols: Optional[List[str]] = None, params={}) -> Tickers:
        await self.load_markets()
        aud_id = '1'
        url = f"{self.urls['api']['public']}/live-rates/{aud_id}/"
        response = await self.fetch(url)
        result = {}
        for asset_id in response.keys():
            if asset_id == aud_id:
                continue
            market = self.markets_by_id.get(f"{asset_id}/{aud_id}")
            if not market:
                continue
            ticker = self.parse_ticker({'assetId': asset_id, **response[asset_id]}, market)
            result[ticker['symbol']] = ticker
        return self.filter_by_array_tickers(result, 'symbol', symbols)

    def parse_ticker(self, ticker: Dict, market: Optional[Market] = None) -> Ticker:
        asset_id = self.safe_string(ticker, 'assetId')
        if asset_id and market is None:
            market = self.safe_market(f"{asset_id}/1")
        symbol = market['symbol'] if market else None
        mid_price = self.safe_string(ticker, 'midPrice')
        ask = self.safe_string(ticker, 'askPrice')
        bid = self.safe_string(ticker, 'bidPrice')
        percentage = self.safe_string(ticker, 'dailyPriceChange')
        detail = self.safe_value(ticker, 'detail', {})
        volume_info = self.safe_value(detail, 'volume', {})
        volume_24h = self.safe_string(volume_info, '24H')
        return self.safe_ticker({
            'symbol': symbol,
            'timestamp': None,
            'datetime': None,
            'high': None,
            'low': None,
            'bid': bid,
            'bidVolume': None,
            'ask': ask,
            'askVolume': None,
            'vwap': None,
            'open': None,
            'close': mid_price,
            'last': mid_price,
            'previousClose': None,
            'change': None,
            'percentage': percentage,
            'average': None,
            'baseVolume': None,
            'quoteVolume': volume_24h,
            'info': ticker,
        }, market)

    async def fetch_ohlcv(self, symbol: str, timeframe: str = '1m', since: Optional[int] = None, limit: Optional[int] = None, params={}) -> List[OHLCV]:
        await self.load_markets()
        market = self.market(symbol)
        resolution = self.timeframes.get(timeframe)
        if not resolution:
            raise BadRequest(f"{self.id} fetch_ohlcv() invalid timeframe {timeframe}")
        side = self.safe_string(params, 'side', 'ask')
        params = self.omit(params, 'side')
        now = self.milliseconds()
        time_end = now
        time_start = since if since else now - 24 * 60 * 60 * 1000
        if limit and limit > 10000:
            raise BadRequest(f"{self.id} fetch_ohlcv() limit cannot exceed 10000")
        query = {'resolution': resolution, 'timeStart': time_start, 'timeEnd': time_end}
        if limit:
            query['limit'] = limit
        path = f"charts/v2/getBars/{market['base']}/{market['quote']}/{side}/"
        url = f"{self.urls['api']['public']}/{path}?{self.urlencode(query)}"
        response = await self.fetch(url)
        return self.parse_ohlcvs(response, market, timeframe, since, limit)

    def parse_ohlcvs(self, ohlcvs: List[Dict], market: Optional[Market] = None, timeframe: str = '1m', since: Optional[int] = None, limit: Optional[int] = None) -> List[OHLCV]:
        return [self.parse_ohlcv(candle, market) for candle in ohlcvs]

    def parse_ohlcv(self, ohlcv: Dict, market: Optional[Market] = None) -> OHLCV:
        return [
            self.safe_integer(ohlcv, 'time'),
            self.safe_number(ohlcv, 'open'),
            self.safe_number(ohlcv, 'high'),
            self.safe_number(ohlcv, 'low'),
            self.safe_number(ohlcv, 'close'),
            self.safe_number(ohlcv, 'volume'),
        ]

    def sign(self, path, api='public', method='GET', params={}, headers=None, body=None):
        url = f"{self.urls['api'][api]}/{self.implode_params(path, params)}"
        query = self.omit(params, self.extract_params(path))
        if api == 'private':
            self.check_required_credentials()
            if not self.access_token:
                self.authenticate()
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f"Bearer {self.access_token}",
                'User-Agent': f"ccxt/{self.version}",
            }
            if method in ['GET', 'DELETE']:
                if query:
                    url += '?' + self.urlencode(query)
            elif method in ['POST', 'PUT']:
                if query:
                    body = json.dumps(query)
        else:
            headers = {
                'Content-Type': 'application/json',
                'User-Agent': f"ccxt/{self.version}",
            }
            if query:
                url += '?' + self.urlencode(query)
        return {'url': url, 'method': method, 'body': body, 'headers': headers}

    async def fetch(self, url, method='GET', headers=None, body=None):
        if self.needs_authentication(url, method):
            if not self.access_token:
                await self.authenticate()
        return await super().fetch(url, method, headers, body)

    def needs_authentication(self, url: str, method: str) -> bool:
        if 'auth/refresh/' in url:
            return False
        base_url = self.urls['api']['private']
        if not url.startswith(base_url):
            return False
        path = url[len(base_url):].lstrip('/')
        query_index = path.find('?')
        if query_index != -1:
            path = path[:query_index]
        private_apis = self.api.get('private', {})
        method_endpoints = private_apis.get(method.lower(), [])
        for endpoint in method_endpoints:
            regex_pattern = '^' + endpoint.replace('{[^}]+}', '[^/]+') + '$'
            if re.match(regex_pattern, path):
                return True
        return False

    def handle_errors(self, status_code, status_text, url, method, response_headers, response_body, response, request_headers, request_body):
        if not response:
            return
        error = self.safe_string(response, 'error')
        message = self.safe_string(response, 'message', error)
        error_code = self.safe_string(response, 'code')
        if error or message or error_code:
            feedback = f"{self.id} {response_body}"
            if status_code in [401, 403]:
                raise AuthenticationError(feedback)
            elif status_code == 429:
                raise RateLimitExceeded(feedback)
            elif status_code == 400:
                raise BadRequest(feedback)
            self.throw_exactly_matched_exception(self.exceptions['exact'], message, feedback)
            self.throw_broadly_matched_exception(self.exceptions['broad'], message, feedback)
            raise ExchangeError(feedback)