import base64
import json
import random
import time
from io import BytesIO

from PIL import Image
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from funcaptcha_challenger import predict

from src.arkose.challenge import Challenge
from src.arkose.session import FunCaptchaSession
from src.config import proxy
from src.utils.Logger import Logger

app = FastAPI()
random.seed(int(time.time()))

support_predict_list = ["3d_rollball_objects", "3d_rollball_animals", "counting", "card", "cardistance",
                        "hand_number_puzzle", "knotsCrossesCircle", "rockstack", "penguins", "penguins-icon", "shadows",
                        "frankenhead", "BrokenJigsawbrokenjigsaw_swap", "conveyor"]
need_to_solve_list = []
session_time = 3600
proxy_time = int(session_time / 60 + 5)
default_method = "chat4"


@app.post("/token")
@app.get("/token")
async def image_solver(request: Request):
    if request.method == 'POST':
        body = await request.json()
        method = body.get("method", default_method)
        proxy = body.get("proxy", get_proxy_session())
        blob = body.get("blob", None)
    else:
        method = request.query_params.get('method', default_method)
        proxy = request.query_params.get("proxy", get_proxy_session())
        blob = request.query_params.get('blob', None)

    if not method:
        return JSONResponse(content={"error": "method is required."}, status_code=400)

    fun = FunCaptchaSession(method=method, blob=blob)
    ch = Challenge(fun, proxy=proxy, timeout=30)
    try:
        arkose_token = ch.get_challenge()

        if "sup=1" in arkose_token:
            ch.get_challenge_game(arkose_token)
            result = {
                "msg": "success",
                "variant": None,
                "solved": True,
                "token": arkose_token,
                "waves": 0,
                "User-Agent": ch.base_headers.ua,
                "proxy": proxy,
            }
            Logger.info(json.dumps(result))
            return JSONResponse(content=result)

        game = ch.get_challenge_game(arkose_token)

        Logger.info(str({
            "Game variant": game.game_variant,
            "Game type": game.type,
            "Game difficulty": game.difficulty,
            "Game waves": game.waves,
            "Game prompt": game.prompt_en
        }))

        if game.game_variant not in need_to_solve_list:
            raise Exception(f"{game.game_variant}, 风控的游戏类型")

        game.pre_get_image()

        answers = {}
        for i in range(game.waves):
            image_base64, image_file_path, image_md5 = game.get_image(i, download=False)

            image_data = base64.b64decode(image_base64)
            image_bytes = BytesIO(image_data)
            image = Image.open(image_bytes)

            if game.game_variant in support_predict_list:
                answer = predict(image, game.game_variant)
            else:
                raise Exception(f"{game.game_variant}, 风控的游戏类型")
            Logger.debug(f"The {i + 1} image's ({image_md5}) answer: {answer}")

            answers[image_file_path] = answer
            answer_result = game.put_answer(i, answer)
            Logger.debug(answer_result)

        result = {
            "msg": "success",
            "variant": game.game_variant,
            "solved": answer_result["solved"],
            "token": ch.arkose_token,
            "waves": game.waves,
            "User-Agent": ch.base_headers.ua,
            "proxy": proxy,
        }
        Logger.info(json.dumps(result))
        return JSONResponse(content=result)

    except Exception as e:
        result = {
            "msg": "Failed: " + str(e),
            "variant": None,
            "solved": False,
            "token": ch.arkose_token,
            "waves": None,
            "User-Agent": ch.base_headers.ua,
            "proxy": proxy,
        }
        Logger.error(str(result))
        return JSONResponse(content=result, status_code=500)


def get_proxy_session():
    return proxy


