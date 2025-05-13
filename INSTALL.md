# Install Pearl-PBX2. Version Alpha 1.
## Internal instructios.

### /etc/asterisk
/etc/asterisk should have the permission to the user which will be used to run django.
For development mode is 'asterisk':
```
chown -R asterisk:asterisk /etc/asterisk
```

Yes, we run Django under user asterisk. Why not?
It allowed us to move the configuration and sound files.



