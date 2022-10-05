import httpx

import json
from time import sleep

from gitfive.lib.objects import Credentials
from gitfive.lib.objects import TMPrinter


class APIInterface():
    """
    This interface permits GitFive to use multi-clients and auto-switch between them,
    if it needs more API calls.

    By default, 1 authenticated + 1 unauthenticated are loaded, but you can add
    more authenticated clients (with other credentials) or more unauthenticated clients by setting proxy to the clients.
    You can add clients in the magazines arrays. 🔫
    """
    def __init__(self, creds: Credentials, tmprinter=TMPrinter()):
        self.tmprinter = tmprinter
        self.clients = {
            "authenticated": {
                "magazine": [
                    httpx.AsyncClient(headers={"Authorization": f"Bearer {creds.token}"})
                ],
            },
            "unauthenticated": {
                "magazine": [
                    httpx.AsyncClient()
                ],
            }
        }
        self.clients["authenticated"]["loaded"] = self.clients["authenticated"]["magazine"][0]
        self.clients["unauthenticated"]["loaded"] = self.clients["unauthenticated"]["magazine"][0]
        self.clients["all"] = {
            "magazine": self.clients["authenticated"]["magazine"] + self.clients["unauthenticated"]["magazine"],
            "loaded": self.clients["authenticated"]["magazine"][0]
        }

    async def verify_rate_limit(self, resource, client):
        req = await client.get("https://api.github.com/rate_limit")
        data = json.loads(req.text)
        if data["resources"][resource]["remaining"]:
            return True
        return False
        
    async def wait_and_reload_client(self, connection_type: str, resource: str):
        while True:
            for client in self.clients[connection_type]["magazine"]:
                remaining = await self.verify_rate_limit(resource, client)
                if remaining:
                    self.clients[connection_type]["loaded"] = client
                    break
            else:
                self.tmprinter.out("Waiting for an API client to be reloaded...")
                sleep(2)
                continue
            break
        self.tmprinter.clear()

    def check_query(self, req: httpx.Response):
        if req.status_code == 403:
            return False
        elif req.status_code in [200, 404, 422]:
            return True
        exit(f"Request returned an unexpected status code : {req.status_code}\nResponse : {req.text}")

    async def query(self, url, connection_type="all"):
        while True:
            req: httpx.Response = await self.clients[connection_type]["loaded"].get(f"https://api.github.com{url}")
            if self.check_query(req):
                data = json.loads(req.text)
                return data

            resource = req.headers["x-ratelimit-resource"]
            await self.wait_and_reload_client(connection_type, resource)