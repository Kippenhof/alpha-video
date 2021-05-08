FROM andrewstech/alpha-video-baseplate:dev
WORKDIR /app
COPY entrypoint.sh entrypoint.sh
RUN chmod 777 entrypoint.sh
COPY /src /app
EXPOSE 5000
ENV FLASK_ENV=development
ENV FLASK_APP=main.py
RUN chmod 777 /app/entrypoint.sh
COPY supervisord.conf /etc/supervisor/supervisord.conf
ENTRYPOINT ["./entrypoint.sh"]
