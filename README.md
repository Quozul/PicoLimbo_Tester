Start the tests using Docker compose:

```shell
docker compose up --build --abort-on-container-exit --exit-code-from pico-tests && docker compose down
```

Connect to the VNC server to see what's going on: http://localhost:6080/vnc.html
