import requests 
from bs4 import BeautifulSoup

url ="https://finance.yahoo.com/quote/AAPL?p=AAPL"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9"
}

response = requests.get(url, headers=headers, timeout=30)

t = response.text

soup = BeautifulSoup(t,features="html.parser")

spans = soup.find_all("li",class_="yf-1qull9i")

finalName = "1y Target Est"
x =0
names =[]
values =[]

namVal={}

for i in range(len(spans)):
    for j in range(len(spans[i].contents)):
        if j==0: #name
            name =spans[i].contents[j].text
            names.append(name)
            print(name)
            print(spans[i].contents)
        if j==2: #value
            value = spans[i].contents[j].text
            values.append(value)
            
        
       
