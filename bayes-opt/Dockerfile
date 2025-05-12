FROM --platform=linux/amd64 almalinux:9

RUN curl -O https://linux-mirrors.fnal.gov/linux/fermilab/almalinux/9/yum-conf-fermilab.rpm

RUN rpm -ivh ./yum-conf-fermilab.rpm

RUN yum install -y fermilab-conf_kerberos

COPY 10-ad-default_ccache /etc/krb5.conf.d/10-ad-default_ccache

#ADD krb5.conf.d /etc/krb5.conf.d 

#yum install https://linux-mirrors.fnal.gov/linux/fermilab/almalinux/9/yum-conf-fermilab.rpm

RUN yum -y install krb5-workstation krb5-libs krb5-devel

ENV KRB5_CONFIG=/etc/krb5.conf

RUN yum install -y python3 python3-pip 

RUN yum install -y gcc gcc-c++ make python3-devel

RUN pip install --upgrade pip setuptools

RUN pip install gssapi

RUN pip install acsys[settings] --extra-index-url https://www-bd.fnal.gov/pip3 && \
    pip install badger-opt  && \
    pip install xopt && \
    pip install matplotlib
    

# Set working directory
WORKDIR /app

# Copy all .py files 
COPY *.py /app/

# Default command
CMD ["bash"]