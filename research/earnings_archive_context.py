"""Bounded original DOM context for report links with split visible labels."""
from html.parser import HTMLParser
import hashlib
import re
from urllib.parse import urljoin, urlsplit


def links(body,url):
    text=body.decode('utf-8');lines=[0]
    lines.extend(m.end() for m in re.finditer('\n',text))
    class Parser(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True);self.stack=[];self.blocks=[];self.skip=0
        def position(self):
            line,column=self.getpos();return lines[line-1]+column
        def handle_starttag(self,tag,attrs):
            if tag in ('script','style','noscript'):self.skip+=1
            if self.skip:return
            if tag in ('br','hr','img','input','meta','link','source','wbr'):return
            if len(self.stack)>=200:raise ValueError('Archive DOM nesting limit exceeded')
            node={'tag':tag,'start':self.position(),'parts':[],'urls':set()};self.stack.append(node)
            if tag=='a':
                target=urljoin(url,dict(attrs).get('href',''))
                if re.search(r'\.pdf$',urlsplit(target).path,re.I):
                    for parent in self.stack:parent['urls'].add(target)
        def handle_endtag(self,tag):
            if tag in ('script','style','noscript'):
                self.skip=max(0,self.skip-1);return
            if self.skip:return
            index=next((i for i in range(len(self.stack)-1,-1,-1) if self.stack[i]['tag']==tag),None)
            if index is None:return
            closing=self.stack[index:];del self.stack[index:]
            for node in closing:
                if node['tag'] in ('div','section','article','li','tr','td','p'):
                    node['end']=text.find('>',self.position())+1;self.blocks.append(node)
        def handle_data(self,value):
            if not self.skip:
                for node in self.stack:node['parts'].append(value)
    parser=Parser();parser.feed(text);parser.close();result=[]
    for node in parser.blocks:
        label=' '.join(' '.join(node['parts']).split())
        if len(node['urls'])!=1 or not 0<len(label)<=500:continue
        if len(set(re.findall(r'\b20\d{2}\b',label)))!=1:continue
        result.append({'url':next(iter(node['urls'])),'title':label,'label_evidence':{
            'rule':'single-document-bounded-dom-context-v1','start':node['start'],'end':node['end'],
            'raw_span_sha256':hashlib.sha256(text[node['start']:node['end']].encode()).hexdigest(),'archive_url':url}})
    return result
