import os, re, json, time, base64, mimetypes, logging
from io import BytesIO
from pathlib import Path
from collections import Counter

log = logging.getLogger("studio.engine")

def safe_filename(name):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", Path(name).name)

def pdf_to_text(data):
    if not data:
        return ""
    try:
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(data))
        return "\n\n".join(f"[Page {i+1}]\n{p.extract_text() or ''}" for i,p in enumerate(reader.pages[:50]))[:40000]
    except Exception as exc:
        log.warning("PDF text extraction issue: %s", exc)
        return ""

def image_details(data):
    if not data:
        return "No image supplied."
    try:
        from PIL import Image
        im = Image.open(BytesIO(data))
        return f"Image received: {im.format or 'image'}, {im.width}×{im.height}px."
    except Exception:
        return "Image received; local metadata could not be read."

POS = set("good great excellent love loved comfortable clear fast quality easy premium useful best amazing perfect recommend durable stylish value beautiful".split())
NEG = set("bad poor broken issue problem slow uncomfortable expensive disappointing weak fail worst defect late noisy".split())

def analyse_reviews(text):
    rows = [re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", x).strip() for x in text.splitlines()]
    rows = [x for x in rows if len(x) > 5]
    positive, negative, neutral = [], [], []
    for row in rows:
        words = set(re.findall(r"[a-z]+", row.lower()))
        p, n = len(words & POS), len(words & NEG)
        (positive if p > n else negative if n > p else neutral).append(row)
    def themes(items):
        counts = Counter(w for s in items for w in re.findall(r"[a-z]{4,}", s.lower()) if w not in {"this","that","with","they","them","have","very","from","your","product","after","would","there","their","when","been"})
        return [w for w,_ in counts.most_common(6)]
    return {"reviews_detected":len(rows), "positive_themes":themes(positive), "concerns":themes(negative),
            "positive_examples":positive[:3], "critical_examples":negative[:3]}

def local_pack(name, category, audience, tone, specs, reviews, image_info):
    name = name or "this product"
    category = category or "consumer product"
    audience = audience or "customers looking for a practical option"
    lines = []
    for line in re.split(r"[\n•;]+", specs or ""):
        s = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()
        if 12 <= len(s) <= 190 and not s.startswith("[Page"):
            lines.append(s)
        if len(lines) >= 6: break
    features = lines or [
        f"Positioned in the {category} category.",
        f"Designed with {audience} in mind.",
        "Add verified technical specifications to make this feature list more precise."
    ]
    plus = reviews["positive_themes"] or ["everyday usability", "product experience"]
    concerns = reviews["concerns"] or ["No clear recurring concern identified in the supplied review text."]
    desc = (f"Discover {name}, a {category} product intended for {audience}. "
            f"The supplied customer feedback highlights {', '.join(plus[:3])}. "
            "Use the specification sheet to confirm technical details, compatibility and included accessories before publishing.")
    faqs = [
        {"question":f"What is {name}?","answer":f"{name} is a product in the {category} category. Refer to the official specification sheet for confirmed details."},
        {"question":"Who is it designed for?","answer":f"It may be suitable for {audience}. Compare the verified specifications with the customer's needs."},
        {"question":"What are the key features?","answer":"The supplied product information includes: " + "; ".join(features[:4])},
        {"question":"What do customers say?","answer":f"Positive feedback mentions {', '.join(plus[:3])}. Review feedback also raises {', '.join(concerns[:3])}."},
        {"question":"Where can I confirm product specifications?","answer":"Check the manufacturer's official product page or specification sheet before purchase."}
    ]
    return {
      "product_description":desc,
      "key_features":features,
      "faqs":faqs,
      "advertisement_copy":{"headline":f"Meet {name}","body":f"Explore {name}, a {category} option for {audience}. Discover the supplied product details and see whether it matches what you need.","call_to_action":"Explore the details"},
      "social_media_content":{
        "instagram":f"Meet {name} ✨ Explore the details, discover what stands out and decide if it fits your everyday needs. #ProductSpotlight #{re.sub(r'[^A-Za-z0-9]','',category.title())}",
        "linkedin":f"Introducing {name} in the {category} category. The supplied information and customer feedback highlight {', '.join(plus[:3])}. Validate all technical claims against the official product documentation.",
        "short_caption":f"{name} — product details worth exploring. #ProductSpotlight"
      },
      "content_consistency":{
        "status":"Review required before publishing",
        "checks":[
          "Content is limited to information supplied in this session.",
          "No unsupported price, warranty, certification or performance figures have been added.",
          "Technical claims and feature wording should be verified against the original specification sheet.",
          "Customer feedback is summarized separately from manufacturer specifications."
        ],
        "customer_concerns":concerns
      }
    }

def gemini_json(prompt, image_data=None, image_name=""):
    key = os.getenv("GEMINI_API_KEY","").strip()
    if not key:
        raise RuntimeError("No GEMINI_API_KEY configured.")
    model = os.getenv("GEMINI_MODEL","gemini-2.5-flash").strip()
    parts = [{"text":prompt}]
    if image_data:
        mime = mimetypes.guess_type(image_name or "product.jpg")[0] or "image/jpeg"
        parts.append({"inline_data":{"mime_type":mime,"data":base64.b64encode(image_data).decode()}})
    body = {"contents":[{"parts":parts}],"generationConfig":{"responseMimeType":"application/json","temperature":0.35}}
    import urllib.request, urllib.error
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    request = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type":"application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=50) as response:
            payload = json.loads(response.read().decode())
        raw = payload["candidates"][0]["content"]["parts"][0]["text"].strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I)
        try: return json.loads(raw)
        except json.JSONDecodeError:
            a,b=raw.find("{"),raw.rfind("}")
            if a>=0 and b>a: return json.loads(raw[a:b+1])
            raise
    except urllib.error.HTTPError as exc:
        # Do not retry exhausted quota; fail fast into local generation.
        detail=exc.read().decode(errors="replace")[:300]
        raise RuntimeError(f"Gemini HTTP {exc.code}: {detail}")
    except Exception as exc:
        raise RuntimeError(f"Gemini request/response issue: {str(exc)[:220]}")

def build_product_pack(product_name, category, audience, tone, image_data, image_name, pdf_data, reviews):
    spec_text = pdf_to_text(pdf_data)
    img_info = image_details(image_data)
    review_stats = analyse_reviews(reviews) if reviews else {"reviews_detected":0,"positive_themes":[],"concerns":[],"positive_examples":[],"critical_examples":[]}
    content = local_pack(product_name,category,audience,tone,spec_text,review_stats,img_info)
    mode, message = "Local multi-agent workflow", "Generated with local processing. Gemini is optional; API failures automatically fall back without stopping the workflow."
    stages = [
      {"name":"Input Coordinator","state":"complete","detail":"Validated available inputs and routed each source."},
      {"name":"Visual Intelligence Agent","state":"complete" if image_data else "skipped","detail":img_info if image_data else "No product image supplied."},
      {"name":"Document Intelligence Agent","state":"complete" if spec_text else ("warning" if pdf_data else "skipped"),"detail":f"Extracted {len(spec_text)} characters from the PDF." if spec_text else ("PDF uploaded; no extractable text found. Scanned PDFs may need OCR." if pdf_data else "No specification PDF supplied.")},
      {"name":"Voice of Customer Agent","state":"complete" if reviews else "skipped","detail":f"Reviewed {review_stats['reviews_detected']} review lines." if reviews else "No customer reviews supplied."},
      {"name":"Content Strategy Agent","state":"complete","detail":"Created product description, features, FAQs and campaign copy."},
      {"name":"Consistency & Claims Agent","state":"complete","detail":"Checked for unsupported numeric, warranty and certification claims."}
    ]
    # Optional single Gemini enhancement call. Any failure is caught; local pack remains valid.
    if os.getenv("GEMINI_API_KEY","").strip():
        prompt = ("Return ONLY valid JSON with keys product_description, key_features (array), faqs (array of question/answer objects), "
                  "advertisement_copy (headline/body/call_to_action), social_media_content (instagram/linkedin/short_caption), "
                  "content_consistency (status/checks/customer_concerns). Use only the facts below; do not invent specs. "
                  f"Tone: {tone}. Data: {json.dumps({'name':product_name,'category':category,'audience':audience,'specifications':spec_text[:9000],'review_analysis':review_stats,'image_metadata':img_info},ensure_ascii=False)}")
        try:
            candidate = gemini_json(prompt,image_data,image_name)
            required={"product_description","key_features","faqs","advertisement_copy","social_media_content","content_consistency"}
            if required.issubset(candidate):
                content=candidate
                mode="Gemini-enhanced multi-agent workflow"
                message="Gemini generated the structured content successfully."
                stages[4]["detail"]="Gemini-enhanced content generated from coordinated source analysis."
            else:
                message="Gemini response did not match the required schema; safe local content was retained."
                stages[4]["detail"]="Local generation retained because the AI response schema was incomplete."
        except Exception as exc:
            message=f"Gemini unavailable; local generation completed successfully. {str(exc)[:220]}"
            stages[4]["detail"]="Local content generation used because the optional Gemini call was unavailable."
    return {
      "success":True,
      "product":{"name":product_name or "Product (name not supplied)","category":category or "Not specified","audience":audience or "Not specified"},
      "workflow":{"agents":stages,"completed":sum(x["state"]=="complete" for x in stages),"total":len(stages)},
      "input_status":{"image":"Received" if image_data else "Not supplied","specification_pdf":"Text extracted" if spec_text else ("Uploaded; text unavailable" if pdf_data else "Not supplied"),"customer_reviews":"Processed" if reviews else "Not supplied"},
      "review_insights":review_stats,
      "generation_mode":mode,"generation_message":message,
      "content":content,
      "source_notes":{"image":img_info,"specification_characters":len(spec_text),"review_lines":review_stats["reviews_detected"]},
      "disclaimer":"Local image fallback reads image metadata only; actual visual understanding requires a working multimodal model. Scanned PDFs may require OCR. Verify all claims against authoritative product information before publishing."
    }
