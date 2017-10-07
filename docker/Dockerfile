FROM centos:7

# Install PIP
RUN yum -y install epel-release && yum clean all
RUN yum -y install python python-pip && yum clean all

# FFMPEG Repos
RUN rpm --import http://li.nux.ro/download/nux/RPM-GPG-KEY-nux.ro
RUN rpm -Uvh http://li.nux.ro/download/nux/dextop/el7/x86_64/nux-dextop-release-0-5.el7.nux.noarch.rpm

# TODO verify required dependenies.
RUN yum -y install numpy scipy python-matplotlib portaudio-devel gcc MySQL-python tkinter ffmpeg ffmpeg-devel

RUN pip install PyAudio
RUN pip install pydub

RUN pip install PyDejavu

WORKDIR /dejavu

CMD ["bash", "-l"]