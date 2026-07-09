---
name: rag-skill
description: Python llm rag
---

```python
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.messages import HumanMessage, SystemMessage, AIMessage
from langchain_google_vertexai import VertexAIEmbeddings  
from dataclasses import dataclass, asdict                                                                                                 
llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash", temperature=1.0, project='vocal-bridge-hackathon', location="global")
llm.invoke("What is 2+2?")

from langchain_google_genai import GoogleGenerativeAIEmbeddings

embeddings = GoogleGenerativeAIEmbeddings(model="gemini-embedding-001", project='vocal-bridge-hackathon', location="global")
vector = embeddings.embed_query("hello, world!")
vector[:5]

from langchain_google_genai import GoogleGenerativeAIEmbeddings

embeddings = GoogleGenerativeAIEmbeddings(model="gemini-embedding-001", project='vocal-bridge-hackathon', location="global")                                                                                                                                                                     
vec = embeddings.embed_query("hello world")                                                                                                                                      
vecs = embeddings.embed_documents(["doc one", "doc two"])

from langchain_core.vectorstores import InMemoryVectorStore

vector_store = InMemoryVectorStore(embeddings)

from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=250, add_start_index=True)
sources = [
    "data/transcripts/dg_2026_06_18.txt"
]
all_chunks = []
for path in sources:
    docs = TextLoader(path).load()
    print(len(docs))
all_splits = text_splitter.split_documents(docs)

print(f"Split transcript into {len(all_splits)} sub-documents.")
```
