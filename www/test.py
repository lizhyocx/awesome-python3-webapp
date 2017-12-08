import orm, asyncio
from models import User, Blog, Comment

async def test(loop):
	await orm.create_pool(loop, host='10.100.21.21', port=3306, user='deployment', password='123456', database='test')
	u = User(name='Test', email='test@example.com', passwd='1234567890', image='about:blank')
	await u.save()

loop = asyncio.get_event_loop()
loop.run_until_complete(asyncio.wait([test(loop)]))
#loop.close()