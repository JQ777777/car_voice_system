from flask import Flask, request, Response
import json

app = Flask(__name__)

@app.route("/feishu", methods=["POST"])
def feishu():
    data = request.get_data(as_text=True)

    # ⚠️ 这里不用 get_json，直接拿原始数据
    body = json.loads(data)

    if "challenge" in body:
        return Response(
            json.dumps({"challenge": body["challenge"]}),
            status=200,
            content_type="application/json"
        )

    return Response(
        json.dumps({"code": 0}),
        status=200,
        content_type="application/json"
    )

app.run(port=5000)