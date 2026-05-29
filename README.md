Start the tests using Docker compose:

```shell
docker compose up --build --abort-on-container-exit --exit-code-from pico-tests && docker compose down
```

Connect to the VNC server to see what's going on: http://localhost:6080/vnc.html

# TODO

Here is a list of improvements I want to make to this tool:

- Being able to test several server configurations such as:
  - Connect to PicoLimbo directly
  - Connect through a Velocity proxy
    - With modern forwarding (from 1.13 to latest version)
    - With legacy forwarding (from 1.7.2)
    - With BungeeGuard forwarding (from 1.7.2)
  - Connect through a BungeeCord proxy (from 1.8 to latest version)
    - With BungeeGuard plugin (from 1.8)
  - Connect through a proxy running either one of the following plugins or all of them:
    - ViaVersion
    - PacketEvents
    - A small custom plugin to hold the player in the configuration state for longer than usual (tests the keep alive)  
      These plugins, when installed on the proxy are known for causing issues with PicoLimbo.
- Keep the player connected for at least 30 seconds to ensure they don't get kicked out from the server

# How to update references

If one new version has a new quit button texture or if the resolution of the game window changes, it is necessary to update the references images to detect properly the quit button.

```shell
docker compose run --build --rm pico-tests python3 update_references.py
```