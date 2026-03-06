password for vpn digitalocean.com is at local location C:\Users\TScot\web-apps\Passwords

digitalocean is linxu based so i had to buy another sever that was windows based went with VirMach ( still in pending state)

Virmach ( need to cancel this and digital ocean if cloudzy works)

cloudzy used github to logon. 


How to check on program in the server. 

Step 1: (Local Laptop) open remote desktop connection or typ mstc and spin up server. 

Step 2: (Server Side-SS) Open powershell and type check status of code first: 

> C:\Users\Administrator> & "C:\nssm\nssm-2.24\win64\nssm.exe" status GovDealsSniper
results: SERVICE_RUNNING

Step 3: (SS) Stop the program and check status:

> C:\Users\Administrator> & "C:\nssm\nssm-2.24\win64\nssm.exe" stop GovDealsSniper
results: unexpected status SERVICE_STOP_PENDING in response to STOP control. 

> C:\Users\Administrator> & "C:\nssm\nssm-2.24\win64\nssm.exe" status GovDealsSniper
results: SERVICE_STOPPED 

Step 4: (SS) Run the program manual on the server. Make sure you're in the right directory first and run. 

> cd C:\Users\Administractor\truck-alert-app
> python -m src.core.autoGovDeals_daemon


let it run and check to see functionality. If you want to stop it "ctrl + C"

