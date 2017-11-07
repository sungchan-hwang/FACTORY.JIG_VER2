0. upstart 설치. (설치하면 부팅 안됨.)
	apt-get install upstart

--------------------------------------------
	
1. apt-get upgrade
   apt-get update
   	
2. samba 설치.
	apt-get install samba samba-common-bin
	
3. requests 설치.
	pip3 install requests
	
4. flask 설치.
	pip3 install flask
	
5. RPi.GPIO 설치.
	pip3 install RPi.GPIO
	
6. pyserial 설치.
	pip3 install pyserial
		
7. dhcp disable
	systemctl disable dhcpcd.service
	systemctl enable networking
	reboot