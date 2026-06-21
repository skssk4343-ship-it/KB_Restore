import requests 
def send(url,title,discription,content):


    data = {
        "username" : "ClOUD Supporting 인증로그",
        "content" : content,
        "avatar_url" : "https://cdn.discordapp.com/icons/910496296249491507/582affa6d3dcde2ad52e40f271483042.webp?size=96"
        
    }


    data["embeds"] = [
        {
            "description" : discription,
            "title" : title,
            "color": 7776511
    
        }
    ]

    result = requests.post(url, json = data)

    try:
        result.raise_for_status()
    except requests.exceptions.HTTPError as err:
        print(err)
    else:
        print("Payload delivered successfully, code {}.".format(result.status_code))

