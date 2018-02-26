# adbkit-init
run `python -m uiautomator2 init` once android device plugin.

## Installation
1. Install nodejs
2. Install dependencies by npm

    ```bash
    npm install
    ```

## Usage
```bash
node main.js --server $SERVER_ADDR
```

How it works.

Use adbkit to trace device. And the following command will call when device plugin

```bash
python -m uiautomator2 init --server $SERVER_ADDR
```

## LICENSE
MIT
