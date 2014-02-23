# Dependencies required by dejavu

* [`pyaudio`](http://people.csail.mit.edu/hubert/pyaudio/)
* [`ffmpeg`](https://github.com/FFmpeg/FFmpeg)
* [`pydub`](http://pydub.com/)
* [`numpy`](http://www.numpy.org/)
* [`scipy`](http://www.scipy.org/)
* [`matplotlib`](http://matplotlib.org/)
* [`MySQLdb`](http://mysql-python.sourceforge.net/MySQLdb.html)

## Dependency installation for Mac OS X

Tested on OS X Mavericks. Needs [Homebrew](http://brew.sh) to be installed.

```
brew install portaudio
brew install ffmpeg

sudo easy_install pyaudio
sudo easy_install pydub
sudo easy_install numpy
sudo easy_install scipy
sudo easy_install matplotlib
sudo easy_install pip

sudo pip install MySQL-python

sudo ln -s /usr/local/mysql/lib/libmysqlclient.18.dylib /usr/lib/libmysqlclient.18.dylib
```
