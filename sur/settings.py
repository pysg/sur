from sur import data

SECRET_KEY = '67eda6e0218611e38ff28c705af62198'
DATABASES = {
  'default': {
    'ENGINE': 'django.db.backends.sqlite3',
    'NAME': data('dev.db'),
    }
}
INSTALLED_APPS = ("sur")