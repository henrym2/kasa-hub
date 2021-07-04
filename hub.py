from logging import warn
from aiohttp import web
import asyncio
import socketio
from kasa import Discover, SmartBulb, SmartPlug
from aiohttp_middlewares import cors_middleware
from aiohttp_middlewares.cors import DEFAULT_ALLOW_HEADERS

sio = socketio.AsyncServer(async_mode='aiohttp', cors_allowed_origins='*', logger=True, engineio_logger=True)


mem = {}
routes = web.RouteTableDef()

'''SOCKET.IO WEB SOCKET CLIENT'''

@sio.on('connect', namespace='/iot')
def connect(sid, environ):
    print("New client")
    return "tst"

@sio.on('getDevice', namespace='/iot')
async def getDevice(sid, data):
    print(data, sid)
    device = mem['devices'][data['host']]
    return {
        device.host: {**device.state_information, 'name': device.alias}
    }

@sio.on('updateDevice', namespace='/iot')
async def updateDevice(sid, data):
    device = mem['devices'][data['host']]
    await asyncio.gather(
        *[deviceActions(action, param, device) for action, param in data['actions'].items()]
        )
    await device.update()
    await emitUpdate()
    return {
        device.host: {**device.state_information, 'name': device.alias}
    }

async def emitUpdate():
    await sio.emit("devicesUpdated", 
        {
            d.host: {**d.state_information, 'name': d.alias} for _, d in mem['devices'].items()
        },
        namespace='/iot'
    )

'''REST CLIENT'''

@routes.get('/iot')
async def index(request):
    return web.Response()

@routes.get('/devices')
async def getDevices(_):
    iotDevices = await Discover.discover()
    returns = {}
    mem['devices'] = iotDevices
    for addr, dev in iotDevices.items():
        returns[addr] = {**dev.state_information, 'name': dev.alias}
    return web.json_response(returns)

@routes.get('/device/{host}')
async def getBulbState(request):
    device = mem['devices'][request.match_info['host']]
    await device.update()
    return web.json_response({
        device.host: {**device.state_information, 'name': device.alias}
    })

@routes.post('/device/{host}')
async def setDeviceState(request):
    device = mem['devices'][request.match_info['host']]
    triggers = await request.json()
    await asyncio.gather(
        *[deviceActions(action, param, device) for action, param in triggers.items()]
        )
    await device.update()
    await emitUpdate()
    return web.json_response({'success': True})

async def deviceActions(action, params, device):
    if isinstance(device, SmartBulb):
        await bulbActions(action, params, device)
    elif isinstance(device, SmartPlug):
        await plugActions(action, params, device)
    else:
        warn("Device not supported (yet)")
        return

async def plugActions(action, _, plug):
    actions = {
        "turn_on": plug.turn_on,
        "turn_off": plug.turn_off
    }
    await actions[action]() 

async def bulbActions(action, params, bulb):
    actions = {
        'alias': bulb.set_alias,
        'brightness': bulb.set_brightness,
        'color_temp': bulb.set_color_temp,
        'hsv': bulb.set_hsv,
        'light_state': bulb.set_light_state,
    }
    await actions[action](params)

async def init():
    print('Server starting')
    print('Discovering...')
    mem['devices'] = await Discover.discover()
    print(f"${mem['devices'].items().__len__()} devices discovered!")
    app = web.Application(
        middlewares=[cors_middleware(allow_all=True)]
    )
    app.add_routes(routes)
    sio.attach(app)
    return app


web.run_app(init())