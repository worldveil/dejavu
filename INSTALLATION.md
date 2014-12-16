# Installation of Dejavu

So far Dejavu has only been tested on Unix systems.

* [`pyaudio`](http://people.csail.mit.edu/hubert/pyaudio/) for grabbing audio from microphone
* [`ffmpeg`](https://github.com/FFmpeg/FFmpeg) for converting audio files to .wav format
* [`pydub`](http://pydub.com/), a Python `ffmpeg` wrapper
* [`numpy`](http://www.numpy.org/) for taking the FFT of audio signals
* [`scipy`](http://www.scipy.org/), used in peak finding algorithms
* [`matplotlib`](http://matplotlib.org/), used for spectrograms and plotting
* [`MySQLdb`](http://mysql-python.sourceforge.net/MySQLdb.html) for interfacing with MySQL databases

For installing `ffmpeg` on Mac OS X, I highly recommend [this post](http://jungels.net/articles/ffmpeg-howto.html).

## Fedora 20+

### Dependency installation on Fedora 20+

Install the dependencies:

    sudo yum install numpy scipy python-matplotlib ffmpeg portaudio-devel
    pip install PyAudio
    pip install pydub
    
Now setup virtualenv ([howto?](http://www.pythoncentral.io/how-to-install-virtualenv-python/)):

    pip install virtualenv
    virtualenv --system-site-packages env_with_system

Install from PyPI:

    source env_with_system/bin/activate
    pip install PyDejavu


You can also install the latest code from GitHub:

    source env_with_system/bin/activate
    pip install https://github.com/worldveil/dejavu/zipball/master

## Max OS X

### Dependency installation for Mac OS X

Tested on OS X Mavericks. An option is to install [Homebrew](http://brew.sh) and do the following:

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

However installing `portaudio` and/or `ffmpeg` from source is also doable. 
