"""Command line for making and fixing skins (also used by the Claude Code skill in
.claude/skills/make-skin). Run from the ParcelWidget folder:

  .venv/bin/python -m skinmaker providers
  .venv/bin/python -m skinmaker make --name "Cat Courier" --desc "..." [--ref pic.png] [--provider openai]
  .venv/bin/python -m skinmaker redo <skin-id> --rows wave,jump      # regenerate some rows only
  .venv/bin/python -m skinmaker assemble <skin-id>                    # rebuild sheet from _work/ (after hand edits)
  .venv/bin/python -m skinmaker preview <skin-id>                     # labelled PNG for checking by eye

API keys come from the widget's encrypted vault (saved from the widget; may ask for Touch ID) or environment variables
(OPENAI_API_KEY, GEMINI_API_KEY, DASHSCOPE_API_KEY, MINIMAX_API_KEY, TENCENTCLOUD_SECRET_ID +
TENCENTCLOUD_SECRET_KEY, STABILITY_API_KEY, REPLICATE_API_TOKEN, FAL_KEY), or --key.
"""
import argparse
import json
import os
import sys

from . import pipeline
from .providers import DEFAULT_PROVIDER, ENV_KEYS, PROVIDERS, get_key

SKINS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui", "skins")


def _progress(done, total, label):
    print("[%d/%d] %s" % (done, total, label), flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m skinmaker")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("providers", help="list providers, default models and whether a key is set")

    def provider_args(p):
        p.add_argument("--provider", choices=list(PROVIDERS))
        p.add_argument("--model", help="override the default model")
        p.add_argument("--base-url", help="override the API endpoint")
        p.add_argument("--key", help="API key (default: the widget's saved key, then environment)")

    m = sub.add_parser("make", help="generate a new skin")
    m.add_argument("--name", required=True)
    m.add_argument("--desc", default="", help="what the character looks like")
    m.add_argument("--ref", help="reference image to keep the look of")
    m.add_argument("--id", help="folder name under ui/skins (default: from the name)")
    provider_args(m)

    r = sub.add_parser("redo", help="regenerate some rows of an existing skin, then reassemble")
    r.add_argument("skin")
    r.add_argument("--rows", required=True, help="comma separated: " + ",".join(pipeline.ROW_NAMES))
    provider_args(r)

    a = sub.add_parser("assemble", help="rebuild sheet.png / skin.json / thumb.png from _work/")
    a.add_argument("skin")
    v = sub.add_parser("preview", help="write a labelled preview PNG")
    v.add_argument("skin")
    v.add_argument("--out")
    args = ap.parse_args(argv)

    if args.cmd == "providers":
        for p in PROVIDERS.values():
            print("%-10s %-32s model=%-26s ref=%-3s key=%s  (%s)" % (
                p.id, p.name, p.model + (" / " + p.edit_model if p.edit_model else ""),
                "yes" if p.supports_ref else "no", "set" if get_key(p.id) else "-", ENV_KEYS.get(p.id)))
        return 0

    if args.cmd in ("make", "redo"):
        job = {}
        if args.cmd == "redo":
            job = json.load(open(os.path.join(SKINS, args.skin, "_work", "job.json"), encoding="utf-8"))
        pid = args.provider or job.get("provider") or DEFAULT_PROVIDER
        key = args.key or get_key(pid)
        if not key:
            sys.exit("No API key for %s: pass --key, save it in the widget, or set %s" % (pid, ENV_KEYS[pid]))
        model = args.model or (job.get("model") if pid == job.get("provider") else None)
        base_url = args.base_url or (job.get("base_url") if pid == job.get("provider") else None)
        if args.cmd == "make":
            ref = open(args.ref, "rb").read() if args.ref else None
            sid, failed = pipeline.make_skin(SKINS, args.name, args.desc, pid, key, ref, model, base_url,
                                             skin_id=args.id, progress=_progress)
        else:
            sid = args.skin
            rows = [x.strip() for x in args.rows.split(",") if x.strip()]
            bad = [x for x in rows if x not in pipeline.ROW_NAMES]
            if bad:
                sys.exit("unknown rows: %s" % ", ".join(bad))
            failed = pipeline.generate_rows(os.path.join(SKINS, sid), rows, pid, key, model, base_url,
                                            progress=_progress)
            pipeline.assemble(os.path.join(SKINS, sid))
        print("preview:", pipeline.preview(os.path.join(SKINS, sid)))
        if failed:
            print("failed rows:", json.dumps(failed, ensure_ascii=False, indent=1))
        print("skin id:", sid)
        return 1 if failed else 0

    skin_dir = os.path.join(SKINS, args.skin)
    if args.cmd == "assemble":
        pipeline.assemble(skin_dir)
        print("preview:", pipeline.preview(skin_dir))
    elif args.cmd == "preview":
        print(pipeline.preview(skin_dir, args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
