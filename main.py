import asyncio
import json
from typing import Optional, Type

import pydantic
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from models import engine, Base, User, Advertisement, Token
from bcrypt import hashpw, checkpw, gensalt
from aiohttp import web


'======== Общение с БД и вспомогательные функции ============================='

Session = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def app_context(app):
    """

    Подключение к БД при запуске
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


@web.middleware
async def session_middleware(request, handler):
    """

    Автоматическое подключение к БД при испольнении обработчика
    """
    async with Session() as session:
        request['session'] = session
        response = await handler(request)
        return response


async def get_item_by_id(item_id, table_name, session):
    """

    Получение объекта из БД по его id
    """
    item = await session.get(table_name, item_id)
    if item is None:
        raise web.HTTPNotFound(
            text=json.dumps({'ERROR': 'item doesn`t exist'}),
            content_type='application/json'
        )
    return item


async def check_token_in_headers(advertisement, request):
    """

    :param advertisement: конкретный объект класса объявлений
    :param request: объект запроса
    :return: True - если user_id создателя  объявления совпадает с user_id владельца переданного
    в headers токена. При несовпадении (владелец токена и создатель объявления являются разными пользователями)
     возвращает False
    """

    token_in_request = request.headers['token']
    token_owner = await get_item_by_id(token_in_request, Token, request['session'])

    if advertisement.user_id == token_owner.user_id:
        return True

    raise web.HTTPUnauthorized(
        text=json.dumps({'ERROR': 'Действие разрешено только владельцу'}),
        content_type='application/json'
    )


'================ Валидация ================================================='

def check_len(value, attribute, min_value):

    '''вспомогательная функция для проверки длины'''
    if len(value) < min_value:
        raise web.HTTPBadRequest(
            text=json.dumps({'ERROR': f'{attribute} is too short, min_lenght = {min_value}'}),
            content_type='application/json'
        )


class CreateUser(pydantic.BaseModel):

    email: str
    password: str

    @pydantic.validator('password')
    def validate_password(cls, value):
        check_len(value, 'password', 5)
        return value


class CreateAdvertisement(pydantic.BaseModel):

    title: str
    description: str

    @pydantic.validator('title')
    def validate_title(cls, value):
        check_len(value, 'title', 8)
        return value

    @pydantic.validator('description')
    def validate_description(cls, value):
        check_len(value, 'description', 5)
        return value


class UpdateAdvertisement(pydantic.BaseModel):

    title: Optional[str]
    description: Optional[str]

    @pydantic.validator('title')
    def validate_title(cls, value):
        check_len(value, 'title', 8)
        return value

    @pydantic.validator('description')
    def validate_description(cls, value):
        check_len(value, 'description', 5)
        return value


async def validate(input_data: dict,
                   validation_model: Type[CreateUser] | Type[CreateAdvertisement] | Type[UpdateAdvertisement]):
    """

    Общая функция валидации входных данных при создании/изменении пользователей/объявлений
    """
    try:
        model_item = validation_model(**input_data)
        return model_item.dict(exclude_none=True)
    except pydantic.ValidationError as err:
        raise web.HTTPBadRequest(
            text=json.dumps({'ERROR': 'incorrect input_data!'}),
            content_type='application/json'
        )


'================================ Вьюхи =========================================='

async def get_hello(request):
    return web.json_response({'status': 'OKS'})


class UserView(web.View):
    """

    Создание, просмотр и удаление пользователей
    """
    async def get(self):
        user = await get_item_by_id(item_id=int(self.request.match_info['user_id']),
                                    table_name=User, session=self.request['session'])

        return web.json_response({'user_id': user.id, 'user_email': user.email,
                                  'created_at': str(user.created_at), 'advs': str(user.advs)})

    async def post(self):
        json_data = await self.request.json()
        validated_data = asyncio.create_task(validate(json_data, CreateUser))  # валидация данных
        validated_data = await validated_data
        validated_data['password'] = hashpw(validated_data['password'].encode(), salt=gensalt()).decode()
        new_user = User(**validated_data)
        self.request['session'].add(new_user)

        try:
            await self.request['session'].commit()
        except IntegrityError:
            raise web.HTTPBadRequest(
                text=json.dumps({'ERROR': 'user is already exists'}),
                content_type='application/json'
            )
        user_token = Token(user_id=new_user.id)  # создание токена при регистрации пользователя
        self.request['session'].add(user_token)
        await self.request['session'].commit()

        return web.json_response({'user_created': f'user_id {new_user.id}', 'token': f'{user_token.id}',
                            'WARNING': 'save your token for authorization!'})

    async def delete(self):
        user = await get_item_by_id(item_id=int(self.request.match_info['user_id']),
                                    table_name=User, session=self.request['session'])
        await self.request['session'].delete(user)
        await self.request['session'].commit()

        return web.json_response({'status OK': f'user {user.email} deleted'})


class AdvertisementView(web.View):
    """

    CRUD объявлений
    """
    async def get(self):
        adv = await get_item_by_id(item_id=int(self.request.match_info['adv_id']),
                                   table_name=Advertisement, session=self.request['session'])

        return web.json_response({'adv_id': adv.id, 'title': adv.title, 'description': adv.description,
                            'created_at': str(adv.created_at), 'created_by': f'user_{adv.user_id}'})

    async def post(self):
        input_data = await self.request.json()
        validated_data = asyncio.create_task(validate(input_data, CreateAdvertisement))  # валидация
        validated_data = await validated_data

        token_in_request = self.request.headers['token']
        token_owner = await get_item_by_id(token_in_request, Token, self.request['session'])
        validated_data['user_id'] = token_owner.user_id  # проставление владельца по токену авторизации

        new_advertisement = Advertisement(**validated_data)
        self.request['session'].add(new_advertisement)

        try:
            await self.request['session'].commit()
        except IntegrityError:
            raise web.HTTPBadRequest(
                text=json.dumps({'ERROR': f'user {input_data["user_id"]} doesn`t exist'}),
                content_type='application/json'
            )
        return web.json_response({'success': f'advertisement id{new_advertisement.id} created with title '
                                           f'"{new_advertisement.title}" by user {new_advertisement.user_id}'})

    async def patch(self):
        input_data = await self.request.json()
        if 'user_id' in input_data:
            raise web.HTTPBadRequest(
                text=json.dumps({'ERROR': 'Смена владельца объявления невозможна'}),
                content_type='application/json'
            )
        validated_data = asyncio.create_task(validate(input_data, UpdateAdvertisement))  # валидация
        validated_data = await validated_data
        adv = await get_item_by_id(item_id=int(self.request.match_info['adv_id']),
                                   table_name=Advertisement, session=self.request['session'])

        await check_token_in_headers(adv, self.request)  # сверка владельца

        for field, value in validated_data.items():
            setattr(adv, field, value)
        self.request['session'].add(adv)
        await self.request['session'].commit()

        return web.json_response({'success': f'advertisement id{adv.id} updated', 'new_data': f'{input_data}'})

    async def delete(self):
        adv = await get_item_by_id(item_id=int(self.request.match_info['adv_id']),
                                   table_name=Advertisement, session=self.request['session'])
        await check_token_in_headers(adv, self.request)  # сверка владельца
        await self.request['session'].delete(adv)
        await self.request['session'].commit()

        return web.json_response({'status OK': f'advertisement id_{adv.id} "{adv.title}" deleted'})


'================================ Запуск приложения =========================================='

async def get_app():
    """

    Запуск приложения app + маршрутизация
    """

    app = web.Application()
    app.cleanup_ctx.append(app_context)
    app.middlewares.append(session_middleware)

    app.add_routes([
        web.get('/', get_hello),
        web.post('/users/', UserView),
        web.get('/users/{user_id:\d+}/', UserView),
        web.delete('/users/{user_id:\d+}/', UserView),
        web.post('/advertisements/', AdvertisementView),
        web.get('/advertisements/{adv_id:\d+}/', AdvertisementView),
        web.patch('/advertisements/{adv_id:\d+}/', AdvertisementView),
        web.delete('/advertisements/{adv_id:\d+}/', AdvertisementView),
    ])

    return app


web.run_app(get_app())


