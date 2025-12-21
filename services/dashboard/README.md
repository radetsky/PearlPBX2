# Operator Dashboard 

This is a idea of Flash Operator Panel, but implemented with my vision.

## Architecture 

AMI -> Listener -> Redis -> Django Channels -> WebSocket -> User 


### Redis 

```
sudo apt install redis-server
```

Python code 
```
pip install redis channels-redis
```


