FROM python:3.10

RUN apt-get update && apt-get install libavahi-compat-libdnssd-dev -y

# Create app directory
WORKDIR /app

# Install app dependencies
COPY ./requirements.txt ./
COPY ./libs ./libs

ENV CRYPTOGRAPHY_DONT_BUILD_RUST=1
RUN pip install -r requirements.txt

# Bundle app source
COPY ./ /app

WORKDIR /app/source
CMD [ "./run_homekit.sh" ] 