FROM registry.access.redhat.com/ubi8:latest
  
USER 0

COPY operator /opt/operator

ENV PYTHON_VERSION=3.8.2

RUN yum install -y \
      gcc \
      openssl-devel \
      bzip2-devel \
      libffi-devel \
      make \
      nss_wrapper \
    && \
    /opt/operator/python3-install.sh && \
    pip3 install --upgrade -r /opt/operator/requirements.txt && \
    mkdir -p /opt/operator/nss && \
    chmod a+rwx /opt/operator/nss

USER 1000

CMD /opt/operator/run.sh
