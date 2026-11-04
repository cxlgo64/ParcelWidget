"""Image-generation providers for skin making.

Every provider has the same interface:

    p = get_provider("openai")
    png_bytes = p.generate(prompt, key, ref=<image bytes or None>, aspect="16:9" | "1:1",
                           model=<optional override>, base_url=<optional override>)

The pipeline always asks for a flat pure-green background and removes it itself, so a
provider does not need to support transparent output.

Model names change often, so each provider's model and endpoint can be overridden in the
widget's Custom Skin panel (or with --model / --base-url on the command line).
Kimi (Moonshot) is not listed: its API reads images but cannot generate them.
"""
import base64
import datetime
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
import uuid

TIMEOUT = 300


class ProviderError(Exception):
    pass


# ---------------------------------------------------------------- HTTP helpers
def _request(method, url, headers=None, body=None, timeout=TIMEOUT):
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        detail = e.read()[:600].decode("utf-8", "replace")
        raise ProviderError("HTTP %d from %s: %s" % (e.code, url.split("?")[0], detail)) from None
    except urllib.error.URLError as e:
        raise ProviderError("Network error for %s: %s" % (url.split("?")[0], e.reason)) from None


def _json(method, url, payload=None, headers=None, timeout=TIMEOUT):
    h = {"Content-Type": "application/json"}
    h.update(headers or {})
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    data, _ = _request(method, url, h, body, timeout)
    try:
        return json.loads(data)
    except ValueError:
        raise ProviderError("Not JSON from %s: %r" % (url, data[:200])) from None


def _multipart(fields, files):
    """fields: {name: str}; files: [(name, filename, bytes, mime)]"""
    boundary = uuid.uuid4().hex
    out = []
    for k, v in fields.items():
        out.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (boundary, k, v)).encode())
    for name, filename, data, mime in files:
        out.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\n"
                    "Content-Type: %s\r\n\r\n" % (boundary, name, filename, mime)).encode() + data + b"\r\n")
    out.append(("--%s--\r\n" % boundary).encode())
    return b"".join(out), "multipart/form-data; boundary=" + boundary


def _download(url):
    if url.startswith("data:"):
        return base64.b64decode(url.split(",", 1)[1])
    data, _ = _request("GET", url)
    return data


def _data_url(img_bytes):
    mime = "image/jpeg" if img_bytes[:3] == b"\xff\xd8\xff" else "image/webp" if img_bytes[8:12] == b"WEBP" else "image/png"
    return "data:%s;base64,%s" % (mime, base64.b64encode(img_bytes).decode())


def _b64(s):
    return base64.b64decode(s)


# ---------------------------------------------------------------- providers
class Provider:
    id = ""
    name = ""
    name_zh = ""
    key_label = "API key"
    key_url = ""
    model = ""             # default model (text -> image)
    edit_model = ""        # default model when a reference image is given ("" = same as model)
    base_url = ""
    supports_ref = True    # can keep the look of a reference image
    max_parallel = 3
    note = ""
    note_zh = ""

    def info(self):
        return {k: getattr(self, k) for k in ("id", "name", "name_zh", "key_label", "key_url", "model", "edit_model",
                                              "base_url", "supports_ref", "note", "note_zh")}

    def generate(self, prompt, key, ref=None, aspect="16:9", model=None, base_url=None):
        raise NotImplementedError


class OpenAI(Provider):
    id, name, name_zh = "openai", "OpenAI (gpt-image)", "OpenAI（gpt-image）"
    key_url = "https://platform.openai.com/api-keys"
    model = "gpt-image-2"
    base_url = "https://api.openai.com"
    note = "Any OpenAI-compatible endpoint works too (change the endpoint)."
    note_zh = "也可以填任何兼容 OpenAI 的接口地址。"

    SIZES = {"16:9": "1536x1024", "1:1": "1024x1024"}

    def generate(self, prompt, key, ref=None, aspect="16:9", model=None, base_url=None):
        base = (base_url or self.base_url).rstrip("/")
        model = model or self.model
        auth = {"Authorization": "Bearer " + key}
        size = self.SIZES.get(aspect, "1024x1024")
        if ref:
            body, ctype = _multipart({"model": model, "prompt": prompt, "size": size, "n": "1"},
                                     [("image[]", "ref.png", ref, "image/png")])
            data, _ = _request("POST", base + "/v1/images/edits", dict(auth, **{"Content-Type": ctype}), body)
            r = json.loads(data)
        else:
            r = _json("POST", base + "/v1/images/generations",
                      {"model": model, "prompt": prompt, "size": size, "n": 1}, auth)
        item = (r.get("data") or [{}])[0]
        if item.get("b64_json"):
            return _b64(item["b64_json"])
        if item.get("url"):
            return _download(item["url"])
        raise ProviderError("OpenAI returned no image: %s" % json.dumps(r)[:300])


class Gemini(Provider):
    id, name, name_zh = "gemini", "Google Gemini (image)", "Google Gemini（图像）"
    key_url = "https://aistudio.google.com/apikey"
    model = "gemini-2.5-flash-image"
    base_url = "https://generativelanguage.googleapis.com"

    def generate(self, prompt, key, ref=None, aspect="16:9", model=None, base_url=None):
        base = (base_url or self.base_url).rstrip("/")
        parts = [{"text": prompt}]
        if ref:
            parts.append({"inline_data": {"mime_type": _data_url(ref)[5:].split(";")[0],
                                          "data": base64.b64encode(ref).decode()}})
        payload = {"contents": [{"parts": parts}],
                   "generationConfig": {"responseModalities": ["TEXT", "IMAGE"],
                                        "imageConfig": {"aspectRatio": aspect}}}
        r = _json("POST", "%s/v1beta/models/%s:generateContent" % (base, model or self.model), payload,
                  {"x-goog-api-key": key})
        for c in r.get("candidates") or []:
            for p in (c.get("content") or {}).get("parts") or []:
                d = p.get("inlineData") or p.get("inline_data")
                if d and d.get("data"):
                    return _b64(d["data"])
        raise ProviderError("Gemini returned no image: %s" % json.dumps(r)[:300])


class Qwen(Provider):
    id, name, name_zh = "qwen", "Qwen (Alibaba Model Studio)", "通义千问（阿里云百炼）"
    key_url = "https://bailian.console.aliyun.com/?apiKey=1"
    model = "qwen-image-plus"
    edit_model = "qwen-image-edit-plus"
    base_url = "https://dashscope.aliyuncs.com"
    note = "International accounts: use https://dashscope-intl.aliyuncs.com as the endpoint."
    note_zh = "国际站账号请把接口地址改成 https://dashscope-intl.aliyuncs.com"

    SIZES = {"16:9": "1664*928", "1:1": "1328*1328"}

    def generate(self, prompt, key, ref=None, aspect="16:9", model=None, base_url=None):
        base = (base_url or self.base_url).rstrip("/")
        content = ([{"image": _data_url(ref)}] if ref else []) + [{"text": prompt}]
        params = {"n": 1, "watermark": False, "prompt_extend": False, "size": self.SIZES.get(aspect, "1328*1328")}
        r = _json("POST", base + "/api/v1/services/aigc/multimodal-generation/generation",
                  {"model": model or (self.edit_model if ref else self.model),
                   "input": {"messages": [{"role": "user", "content": content}]}, "parameters": params},
                  {"Authorization": "Bearer " + key})
        try:
            for c in r["output"]["choices"][0]["message"]["content"]:
                if c.get("image"):
                    return _download(c["image"])
        except (KeyError, IndexError, TypeError):
            pass
        raise ProviderError("Qwen returned no image: %s" % json.dumps(r, ensure_ascii=False)[:300])


class MiniMax(Provider):
    id, name, name_zh = "minimax", "MiniMax (image-01)", "MiniMax（image-01）"
    key_url = "https://platform.minimaxi.com/user-center/basic-information/interface-key"
    model = "image-01"
    base_url = "https://api.minimaxi.com"
    note = "International accounts: use https://api.minimax.io as the endpoint."
    note_zh = "国际站账号请把接口地址改成 https://api.minimax.io"

    def generate(self, prompt, key, ref=None, aspect="16:9", model=None, base_url=None):
        base = (base_url or self.base_url).rstrip("/")
        payload = {"model": model or self.model, "prompt": prompt[:1500], "aspect_ratio": aspect,
                   "response_format": "base64", "n": 1, "prompt_optimizer": False}
        if ref:
            payload["subject_reference"] = [{"type": "character", "image_file": _data_url(ref)}]
        r = _json("POST", base + "/v1/image_generation", payload, {"Authorization": "Bearer " + key})
        br = r.get("base_resp") or {}
        if br.get("status_code") not in (0, None):
            raise ProviderError("MiniMax: %s" % br.get("status_msg"))
        imgs = (r.get("data") or {}).get("image_base64") or []
        if imgs:
            return _b64(imgs[0])
        urls = (r.get("data") or {}).get("image_urls") or []
        if urls:
            return _download(urls[0])
        raise ProviderError("MiniMax returned no image: %s" % json.dumps(r, ensure_ascii=False)[:300])


class Hunyuan(Provider):
    """Tencent Cloud Hunyuan image generation (async job API, TC3-HMAC-SHA256 signed)."""
    id, name, name_zh = "hunyuan", "Tencent Hunyuan (Tencent Cloud)", "腾讯混元（腾讯云）"
    key_label = "SecretId:SecretKey"
    key_url = "https://console.cloud.tencent.com/cam/capi"
    model = "SubmitHunyuanImageJob"
    base_url = "https://hunyuan.tencentcloudapi.com"
    supports_ref = False
    max_parallel = 1          # one job at a time by default on Tencent Cloud
    note = "Enter SecretId and SecretKey joined by a colon. Text only: no reference image."
    note_zh = "填 SecretId 和 SecretKey，中间用英文冒号隔开。只支持文字描述，不支持参考图。"

    RES = {"16:9": "1280:720", "1:1": "1024:1024"}

    def _call(self, base, sid, skey, action, params):
        host = base.split("://", 1)[-1].strip("/")
        ts = int(time.time())
        date = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%d")
        payload = json.dumps(params)
        canonical = "POST\n/\n\ncontent-type:application/json; charset=utf-8\nhost:%s\nx-tc-action:%s\n\n" \
                    "content-type;host;x-tc-action\n%s" % (host, action.lower(), hashlib.sha256(payload.encode()).hexdigest())
        scope = "%s/hunyuan/tc3_request" % date
        to_sign = "TC3-HMAC-SHA256\n%d\n%s\n%s" % (ts, scope, hashlib.sha256(canonical.encode()).hexdigest())

        def h(k, msg):
            return hmac.new(k, msg.encode(), hashlib.sha256).digest()
        k = h(h(h(("TC3" + skey).encode(), date), "hunyuan"), "tc3_request")
        sig = hmac.new(k, to_sign.encode(), hashlib.sha256).hexdigest()
        headers = {
            "Authorization": "TC3-HMAC-SHA256 Credential=%s/%s, SignedHeaders=content-type;host;x-tc-action, Signature=%s"
                             % (sid, scope, sig),
            "Content-Type": "application/json; charset=utf-8", "Host": host, "X-TC-Action": action,
            "X-TC-Timestamp": str(ts), "X-TC-Version": "2023-09-01", "X-TC-Region": "ap-guangzhou",
        }
        data, _ = _request("POST", "https://" + host, headers, payload.encode())
        r = json.loads(data).get("Response", {})
        if r.get("Error"):
            raise ProviderError("Hunyuan: %s %s" % (r["Error"].get("Code"), r["Error"].get("Message")))
        return r

    def generate(self, prompt, key, ref=None, aspect="16:9", model=None, base_url=None):
        if ":" not in key:
            raise ProviderError("Hunyuan needs 'SecretId:SecretKey'")
        sid, skey = key.split(":", 1)
        base = base_url or self.base_url
        job = self._call(base, sid.strip(), skey.strip(), model or self.model,
                         {"Prompt": prompt[:1024], "Resolution": self.RES.get(aspect, "1024:1024"), "LogoAdd": 0,
                          "Revise": 0})
        jid = job.get("JobId")
        query = (model or self.model).replace("Submit", "Query")
        deadline = time.time() + 600
        while time.time() < deadline:
            time.sleep(4)
            r = self._call(base, sid.strip(), skey.strip(), query, {"JobId": jid})
            code = str(r.get("JobStatusCode"))
            if code == "5":
                return _download((r.get("ResultImage") or [""])[0])
            if code == "4":
                raise ProviderError("Hunyuan job failed: %s" % (r.get("JobErrorMsg") or r))
        raise ProviderError("Hunyuan job timed out")


class Stability(Provider):
    id, name, name_zh = "stability", "Stability AI", "Stability AI"
    key_url = "https://platform.stability.ai/account/keys"
    model = "stable-image/generate/core"
    edit_model = "stable-image/control/style"
    base_url = "https://api.stability.ai"
    note = "With a reference image it copies the style, not the exact character."
    note_zh = "有参考图时只能参考画风，角色不一定完全一致。"

    def generate(self, prompt, key, ref=None, aspect="16:9", model=None, base_url=None):
        base = (base_url or self.base_url).rstrip("/")
        fields = {"prompt": prompt[:10000], "aspect_ratio": aspect, "output_format": "png"}
        files = []
        if ref:
            fields["fidelity"] = "0.7"
            files.append(("image", "ref.png", ref, "image/png"))
        body, ctype = _multipart(fields, files)
        path = model or (self.edit_model if ref else self.model)
        data, rtype = _request("POST", "%s/v2beta/%s" % (base, path),
                               {"Authorization": "Bearer " + key, "Accept": "image/*", "Content-Type": ctype}, body)
        if not rtype.startswith("image/"):
            raise ProviderError("Stability returned no image: %r" % data[:300])
        return data


class Replicate(Provider):
    id, name, name_zh = "replicate", "Replicate", "Replicate"
    key_label = "API token"
    key_url = "https://replicate.com/account/api-tokens"
    model = "google/nano-banana"
    base_url = "https://api.replicate.com"
    note = "Model is owner/name on replicate.com (e.g. black-forest-labs/flux-kontext-pro)."
    note_zh = "模型填 replicate.com 上的 owner/name（例如 black-forest-labs/flux-kontext-pro）。"

    def generate(self, prompt, key, ref=None, aspect="16:9", model=None, base_url=None):
        base = (base_url or self.base_url).rstrip("/")
        model = model or self.model
        inp = {"prompt": prompt, "aspect_ratio": aspect, "output_format": "png"}
        if ref:
            if "kontext" in model:
                inp["input_image"] = _data_url(ref)
            else:
                inp["image_input"] = [_data_url(ref)]
        auth = {"Authorization": "Bearer " + key}
        r = _json("POST", "%s/v1/models/%s/predictions" % (base, model), {"input": inp}, dict(auth, Prefer="wait=60"))
        deadline = time.time() + 600
        while r.get("status") not in ("succeeded", "failed", "canceled") and time.time() < deadline:
            time.sleep(3)
            r = _json("GET", r["urls"]["get"], None, auth)
        if r.get("status") != "succeeded":
            raise ProviderError("Replicate: %s" % (r.get("error") or r.get("status")))
        out = r.get("output")
        url = out[0] if isinstance(out, list) else out
        if not url:
            raise ProviderError("Replicate returned no image")
        return _download(url)


class Fal(Provider):
    id, name, name_zh = "fal", "fal.ai", "fal.ai"
    key_url = "https://fal.ai/dashboard/keys"
    model = "fal-ai/nano-banana"
    edit_model = "fal-ai/nano-banana/edit"
    base_url = "https://fal.run"
    note = "Model is the fal endpoint id (e.g. fal-ai/flux-pro/kontext)."
    note_zh = "模型填 fal 的接口 id（例如 fal-ai/flux-pro/kontext）。"

    def generate(self, prompt, key, ref=None, aspect="16:9", model=None, base_url=None):
        base = (base_url or self.base_url).rstrip("/")
        model = model or (self.edit_model if ref else self.model)
        payload = {"prompt": prompt, "num_images": 1, "output_format": "png", "aspect_ratio": aspect}
        if ref:
            if "kontext" in model:
                payload["image_url"] = _data_url(ref)
            else:
                payload["image_urls"] = [_data_url(ref)]
        r = _json("POST", "%s/%s" % (base, model), payload, {"Authorization": "Key " + key})
        imgs = r.get("images") or ([r["image"]] if r.get("image") else [])
        if not imgs:
            raise ProviderError("fal returned no image: %s" % json.dumps(r)[:300])
        return _download(imgs[0]["url"])


PROVIDERS = {p.id: p for p in (OpenAI(), Gemini(), Qwen(), MiniMax(), Hunyuan(), Stability(), Replicate(), Fal())}
DEFAULT_PROVIDER = "openai"


def get_provider(pid):
    if pid not in PROVIDERS:
        raise ProviderError("Unknown provider %r (choose from %s)" % (pid, ", ".join(PROVIDERS)))
    return PROVIDERS[pid]


# ---------------------------------------------------------------- keys
KEYRING_SERVICE = "ParcelWidget-ImageAPI"
ENV_KEYS = {"openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY", "qwen": "DASHSCOPE_API_KEY",
            "minimax": "MINIMAX_API_KEY", "hunyuan": "TENCENTCLOUD_SECRET", "stability": "STABILITY_API_KEY",
            "replicate": "REPLICATE_API_TOKEN", "fal": "FAL_KEY"}


def get_key(pid):
    """Keychain first (set from the widget), then the environment variable."""
    import os
    try:
        import keyring
        k = keyring.get_password(KEYRING_SERVICE, pid)
        if k:
            return k
    except Exception:
        pass
    if pid == "hunyuan" and os.environ.get("TENCENTCLOUD_SECRET_ID"):
        return "%s:%s" % (os.environ["TENCENTCLOUD_SECRET_ID"], os.environ.get("TENCENTCLOUD_SECRET_KEY", ""))
    return os.environ.get(ENV_KEYS.get(pid, ""), "")


def set_key(pid, key):
    import keyring  # macOS Keychain, never a plain file
    keyring.set_password(KEYRING_SERVICE, pid, key)
