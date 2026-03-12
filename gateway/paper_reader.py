"""
论文阅读器后端 API
与 XiaoMengCore 集成，可一起部署到服务器
"""

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from pathlib import Path
import shutil
import json
import re
import time

router = APIRouter(prefix="/paper", tags=["论文阅读器"])

PAPERS_DIR = Path("data/papers")
PAPERS_DIR.mkdir(parents=True, exist_ok=True)


@router.get("/reader", response_class=HTMLResponse)
async def paper_reader_page():
    """论文阅读器前端页面"""
    html_path = Path("web/paper_reader.html")
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>前端文件不存在</h1><p>请检查 web/paper_reader.html</p>")


class ChatMessage(BaseModel):
    paper_id: str
    message: str
    history: List[Dict[str, str]] = []


class AnalysisRequest(BaseModel):
    paper_id: str
    analysis_type: str = "summary"


def extract_text_from_pdf(file_path: str) -> Dict[str, Any]:
    """从 PDF 提取文本"""
    try:
        import fitz
    except ImportError:
        return {"success": False, "error": "请安装 PyMuPDF: pip install PyMuPDF", "text": "", "pages": []}
    
    try:
        doc = fitz.open(file_path)
        pages = []
        full_text = ""
        
        for page_num, page in enumerate(doc):
            text = page.get_text()
            pages.append({"page_num": page_num + 1, "text": text})
            full_text += text + "\n"
        
        doc.close()
        return {"success": True, "text": full_text, "pages": pages, "page_count": len(pages)}
    except Exception as e:
        return {"success": False, "error": str(e), "text": "", "pages": []}


def extract_paper_structure(text: str) -> Dict[str, str]:
    """提取论文结构"""
    structure = {"title": "", "abstract": "", "introduction": "", "methods": "", "results": "", "conclusion": ""}
    
    patterns = {
        "abstract": [r"(?i)abstract\s*[:\n]?(.*?)(?=\n\s*(?:1\.|introduction|keywords))", r"(?i)摘要\s*[:\n]?(.*?)(?=\n\s*(?:1\.|引言))"],
        "introduction": [r"(?i)(?:1\.?\s*)?introduction\s*[:\n]?(.*?)(?=\n\s*(?:2\.|methods))", r"(?i)(?:1\.?\s*)?引言\s*[:\n]?(.*?)(?=\n\s*(?:2\.|方法))"],
        "methods": [r"(?i)(?:\d+\.?\s*)?(?:methods?|methodology)\s*[:\n]?(.*?)(?=\n\s*(?:\d+\.|experiments?|results?))", r"(?i)(?:\d+\.?\s*)?方法\s*[:\n]?(.*?)(?=\n\s*(?:\d+\.|实验|结果))"],
        "results": [r"(?i)(?:\d+\.?\s*)?(?:results?|experiments?)\s*[:\n]?(.*?)(?=\n\s*(?:\d+\.|discussion|conclusion))", r"(?i)(?:\d+\.?\s*)?(?:结果|实验)\s*[:\n]?(.*?)(?=\n\s*(?:\d+\.|讨论|结论))"],
        "conclusion": [r"(?i)(?:\d+\.?\s*)?(?:conclusions?|summary)\s*[:\n]?(.*?)(?=\n\s*(?:\d+\.|references|$))", r"(?i)(?:\d+\.?\s*)?(?:结论|总结)\s*[:\n]?(.*?)(?=\n\s*(?:\d+\.|参考文献|$))"]
    }
    
    for key, pats in patterns.items():
        for pat in pats:
            match = re.search(pat, text, re.DOTALL)
            if match:
                structure[key] = match.group(1).strip()[:3000]
                break
    
    lines = text.strip().split('\n')
    for line in lines[:20]:
        line = line.strip()
        if 10 < len(line) < 200 and not any(kw in line.lower() for kw in ['abstract', 'arxiv', 'vol.']):
            structure["title"] = line
            break
    
    return structure


async def call_llm(prompt: str, max_tokens: int = 1500) -> str:
    """调用 XiaoMengCore 的 LLM 客户端"""
    try:
        from core.llm_client import LLMClient
        client = LLMClient.get_instance()
        
        response = await client.chat(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens
        )
        return response.get("content", "分析失败")
    except Exception as e:
        return f"AI 调用失败: {str(e)}"


@router.post("/upload")
async def upload_paper(file: UploadFile = File(...)):
    """上传论文"""
    if not file.filename.endswith('.pdf'):
        return JSONResponse({"success": False, "error": "只支持 PDF 文件"})
    
    paper_id = f"paper_{int(time.time())}"
    file_path = PAPERS_DIR / f"{paper_id}.pdf"
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    result = extract_text_from_pdf(str(file_path))
    
    if not result["success"]:
        return JSONResponse({"success": False, "error": result["error"]})
    
    structure = extract_paper_structure(result["text"])
    
    meta = {
        "paper_id": paper_id,
        "filename": file.filename,
        "title": structure["title"] or file.filename,
        "upload_time": time.strftime("%Y-%m-%d %H:%M"),
        "page_count": result["page_count"],
        "file_size": file_path.stat().st_size,
        "structure": structure
    }
    
    with open(PAPERS_DIR / f"{paper_id}.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    
    with open(PAPERS_DIR / f"{paper_id}.txt", "w", encoding="utf-8") as f:
        f.write(result["text"])
    
    return JSONResponse({"success": True, "paper": meta})


@router.get("/list")
async def list_papers():
    """列出所有论文"""
    papers = []
    for meta_file in PAPERS_DIR.glob("*.json"):
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                papers.append(json.load(f))
        except:
            pass
    papers.sort(key=lambda x: x.get("upload_time", ""), reverse=True)
    return {"papers": papers}


@router.get("/detail/{paper_id}")
async def get_paper(paper_id: str):
    """获取论文详情"""
    meta_path = PAPERS_DIR / f"{paper_id}.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="论文不存在")
    
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    
    text_path = PAPERS_DIR / f"{paper_id}.txt"
    if text_path.exists():
        with open(text_path, "r", encoding="utf-8") as f:
            meta["full_text"] = f.read()
    
    return meta


@router.delete("/delete/{paper_id}")
async def delete_paper(paper_id: str):
    """删除论文"""
    for ext in [".pdf", ".json", ".txt"]:
        file_path = PAPERS_DIR / f"{paper_id}{ext}"
        if file_path.exists():
            file_path.unlink()
    return {"success": True}


@router.post("/analyze")
async def analyze_paper(request: AnalysisRequest):
    """AI 分析论文"""
    meta_path = PAPERS_DIR / f"{request.paper_id}.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="论文不存在")
    
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    
    structure = meta.get("structure", {})
    
    prompts = {
        "summary": f"""请分析以下论文，生成中文摘要。

标题: {structure.get('title', '未知')}

摘要: {structure.get('abstract', '无')[:1500]}

方法: {structure.get('methods', '无')[:1000]}

结果: {structure.get('results', '无')[:1000]}

请输出：
## 论文概述
[一句话概括]

## 主要贡献
1. [贡献1]
2. [贡献2]

## 方法创新
[简述]

## 实验结果
[关键发现]""",
        
        "contribution": f"""分析论文的主要贡献。

标题: {structure.get('title', '未知')}
摘要: {structure.get('abstract', '无')}
方法: {structure.get('methods', '无')[:2000]}

请列出：
1. 主要贡献（3-5点）
2. 方法创新点
3. 与现有工作的区别""",
        
        "method": f"""详细分析论文的方法。

标题: {structure.get('title', '未知')}
方法: {structure.get('methods', '无')[:3000]}

请分析：
1. 核心思想
2. 技术细节
3. 实现步骤
4. 优缺点"""
    }
    
    result = await call_llm(prompts.get(request.analysis_type, prompts["summary"]))
    return {"success": True, "analysis_type": request.analysis_type, "result": result}


@router.post("/chat")
async def chat_about_paper(message: ChatMessage):
    """关于论文的对话"""
    meta_path = PAPERS_DIR / f"{message.paper_id}.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="论文不存在")
    
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    
    text_path = PAPERS_DIR / f"{message.paper_id}.txt"
    full_text = ""
    if text_path.exists():
        with open(text_path, "r", encoding="utf-8") as f:
            full_text = f.read()[:6000]
    
    try:
        from core.llm_client import LLMClient
        client = LLMClient.get_instance()
        
        messages = [
            {"role": "system", "content": f"你是论文助手。论文标题: {meta.get('title', '未知')}\n\n内容:\n{full_text}"},
            *[{"role": m["role"], "content": m["content"]} for m in message.history[-10:]],
            {"role": "user", "content": message.message}
        ]
        
        response = await client.chat(messages=messages, max_tokens=1000)
        
        return {"success": True, "response": response.get("content", "")}
    except Exception as e:
        return {"success": False, "error": str(e)}
