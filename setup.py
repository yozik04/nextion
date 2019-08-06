from setuptools import setup

setup(
    name='nextion',
    version='0.0.1',
    packages=['tests', 'nextion'],
    url='https://github.com/yozik04/python-nextion',
    license='MIT',
    author='jevgenik',
    author_email='yozik04@gmail.com',
    description='Nextion display serial client',
    tests_require=[
        'pytest',
        'pytest-asyncio'
    ]
)
