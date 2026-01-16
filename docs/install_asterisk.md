#!/bin/sh

apt-get update && apt-get install -y locales && localedef -i en_US -c -f UTF-8 -A /usr/share/locale/locale.alias en_US.UTF-8
DEBIAN_FRONTEND="noninteractive" apt-get -y install tzdata less
apt-get install -y pkg-config build-essential libedit-dev uuid-dev libxml2-dev libsqlite3-dev libspandsp-dev libpq-dev postgresql-client postgresql vim screen wget git curl libnewt-dev libssl-dev subversion libspeex-dev libspeexdsp-dev libogg-dev libvorbis-dev libasound2-dev portaudio19-dev libcurl4-openssl-dev xmlstarlet bison flex libpq-dev unixodbc-dev libneon27-dev libgmime-3.0-dev liblua5.2-dev liburiparser-dev libxslt1-dev libssl-dev freetds-dev libosptk-dev libjack-jackd2-dev bash libcap-dev libsnmp-dev libiksemel-dev libcorosync-common-dev libcpg-dev libcfg-dev libnewt-dev libpopt-dev libical-dev libspandsp-dev libresample1-dev binutils-dev libsrtp2-dev libgsm1-dev zlib1g-dev libldap2-dev libcodec2-dev libfftw3-dev libsndfile1-dev libunbound-dev libopus-dev redis

wget https://downloads.asterisk.org/pub/telephony/asterisk/asterisk-22-current.tar.gz -O /usr/src/asterisk-current.tar.gz
cd /usr/src && tar zxvf ./asterisk-current.tar.gz
cd /usr/src/asterisk-22.7.0 && ./contrib/scripts/get_mp3_source.sh
cd /usr/src/asterisk-22.7.0 && ./configure --prefix=/ --enable-dev-mode --with-crypto --with-postgres --with-spandsp --with-jansson-bundled --with-opus && make menuselect.makeopts && ./menuselect/menuselect --enable codec_opus && make && make install && make basic-pbx


sudo groupadd asterisk
sudo useradd -r -d /var/lib/asterisk -g asterisk asterisk
sudo usermod -aG audio,dialout asterisk
sudo chown -R asterisk:asterisk /etc/asterisk
sudo chown -R asterisk:asterisk /var/{lib,log,spool}/asterisk
sudo chown -R asterisk:asterisk /usr/lib/asterisk
sudo chmod -R 750 /var/{lib,log,run,spool}/asterisk /usr/lib/asterisk /etc/asterisk

sudo -u postgres psql
```
postgres=# create user asterisk with password '3pJJ3s8yv1R07syheXoynw=='
postgres=# create database asterisk owner asterisk;
```

check:

sudo -u asterisk psql
```
psql (17.6 (Debian 17.6-0+deb13u1))
Введіть "help", щоб отримати допомогу.

asterisk=> \d
Не знайдено жодного відношення.
asterisk=> \q
```

cd /usr/local
git clone git@github.com:radetsky/PearlPBX2.git

cd /usr/local/PearlPBX2
sudo apt install python3-venv
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

sudo apt install tftpd-hpa
sudo mkdir -p /var/lib/tftpboot
sudo chown asterisk:asterisk /var/lib/tftpboot

```
# /etc/default/tftpd-hpa

TFTP_USERNAME="asterisk"
TFTP_DIRECTORY="/var/lib/tftpboot"
TFTP_ADDRESS=":69"
TFTP_OPTIONS="--secure"
```
sudo systemctl start tftpd-hpa
sudo netstat -lunp

cp env.sample .env

```
./manage.py showmigrations
```
to check correct settings for the database connections

```
./manage.py migrate
./manage.py createsuperuser
```

sudo chown -R asterisk:asterisk /usr/local/PearlPBX2
sudo -u asterisk /usr/local/PearlPBX2/.venv/bin/python manage.py collectstatic

```
sudo -u asterisk bash
/usr/local/PearlPBX2/.venv/bin/gunicorn pbx.wsgi:application --bind 127.0.0.1:8000

remove export from /usr/local/PearlPBX2/.env
leave only VAR=VAL

sudo cp services/PearlPBX2.service /etc/systemd/system/pearlpbx2-asgi.service
sudo systemctl daemon-reload
sudo systemctl enable pearlpbx2-asgi
sudo systemctl start pearlpbx2-asgi
sudo systemctl status pearlpbx2-asgi

sudo apt install nginx
sudo cp service/PearlPBX.nginx /etc/nginx/sites-available/pearlpbx2
sudo ln -s /etc/nginx/sites-available/pearlpbx2 /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx

# Run Asterisk, FastAGI, Callback, DashBoard services
# create IPTables rules
# check, reboot, etc.
