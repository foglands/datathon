"""Build the English submission PDFs from their versioned Markdown sources."""

from html import escape
from pathlib import Path
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parents[1]
NAVY = colors.HexColor('#12243A')
TEAL = colors.HexColor('#087C78')
PALE = colors.HexColor('#EFF6F7')
GRAY = colors.HexColor('#506174')
LINE = colors.HexColor('#D6E3E8')
REPO = 'https://github.com/foglands/datathon/blob/architecture-completion-20261115/'


def register_fonts():
    candidates = [
        (Path('/System/Library/Fonts/Supplemental'), 'Arial.ttf', 'Arial Bold.ttf', 'Arial Italic.ttf'),
        (Path('/usr/share/fonts/truetype/dejavu'), 'DejaVuSans.ttf', 'DejaVuSans-Bold.ttf', 'DejaVuSans-Oblique.ttf'),
    ]
    for folder, normal, bold, italic in candidates:
        if all((folder / name).is_file() for name in (normal, bold, italic)):
            for key, name in [('Body', normal), ('Body-Bold', bold), ('Body-Italic', italic)]:
                pdfmetrics.registerFont(TTFont(key, folder / name))
            pdfmetrics.registerFontFamily('Body', normal='Body', bold='Body-Bold', italic='Body-Italic', boldItalic='Body-Bold')
            return 'Body', 'Body-Bold'
    return 'Helvetica', 'Helvetica-Bold'


FONT, BOLD = register_fonts()


def inline(text, source):
    text = text.replace('—', ' - ').replace('–', '-').replace('’', "'").replace('“', '"').replace('”', '"')
    text = escape(text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', lambda m: '<link color="#087C78" href="' + (
        m[2] if m[2].startswith('https://') else REPO + str((source.parent / m[2]).resolve().relative_to(ROOT))
    ) + '">' + m[1] + '</link>', text)
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'`([^`]+)`', r'<font name="Courier">\1</font>', text)
    return text


class Architecture(Flowable):
    def __init__(self):
        Flowable.__init__(self)
        self.width, self.height = 528, 180

    def draw(self):
        c = self.canv
        boxes = {
            'a': (0, 136, 'Question + context'), 'b': (184, 136, 'Analysis tasks'),
            'c': (368, 136, 'Evidence + Python'), 'd': (368, 64, 'Claim synthesis'),
            'e': (184, 64, 'Claim / task review'), 'f': (0, 64, 'Report + status'),
        }
        def arrow(x1, y1, x2, y2):
            from math import atan2, cos, sin
            c.setStrokeColor(TEAL)
            c.setLineWidth(1)
            c.line(x1, y1, x2, y2)
            angle = atan2(y2 - y1, x2 - x1)
            for delta in (-.45, .45):
                c.line(x2, y2, x2 - 5*cos(angle+delta), y2 - 5*sin(angle+delta))
        for left, right in [('a','b'), ('b','c')]:
            x1,y1,_ = boxes[left]; x2,y2,_ = boxes[right]
            arrow(x1+120,y1+17,x2,y2+17)
        arrow(428,136,428,98)
        arrow(368,81,304,81)
        arrow(184,81,120,81)
        c.setStrokeColor(TEAL)
        c.lines([(244,64,244,20),(244,20,428,20)])
        arrow(428,20,428,64)
        c.lines([(244,98,244,116),(244,116,480,116)])
        arrow(480,116,480,136)
        c.setFillColor(GRAY); c.setFont(FONT,7.5)
        c.drawString(285,25,'Revise claims or scope')
        c.drawString(285,120,'Retrieve missing evidence')
        for x,y,label in boxes.values():
            c.setFillColor(PALE); c.setStrokeColor(LINE)
            c.roundRect(x,y,120,34,5,fill=1,stroke=1)
            c.setFillColor(NAVY); c.setFont(BOLD,8.1)
            c.drawCentredString(x+60,y+13,label)


def render(name, compact=False):
    source = ROOT / 'submission' / (name + '.md')
    output = source.with_suffix('.pdf')
    size, leading = (9.2,12.4) if compact else (9.5,13.0)
    body = ParagraphStyle('body',fontName=FONT,fontSize=size,leading=leading,textColor=NAVY,spaceAfter=7 if compact else 5)
    title = ParagraphStyle('title',parent=body,fontName=BOLD,fontSize=23,leading=28,spaceAfter=12)
    h2 = ParagraphStyle('h2',parent=body,fontName=BOLD,fontSize=12.2,leading=16,textColor=TEAL,spaceBefore=9,spaceAfter=6,keepWithNext=True)
    h3 = ParagraphStyle('h3',parent=h2,fontSize=10.2,leading=14)
    cell = ParagraphStyle('cell',parent=body,fontSize=8.6 if compact else 8.4,leading=11.8,spaceAfter=0)
    code = ParagraphStyle('code',parent=body,fontName='Courier',fontSize=7.7,leading=10.2,backColor=PALE,borderPadding=6)
    story, lines = [], source.read_text(encoding='utf-8').splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1; continue
        if line.startswith('```'):
            language=line[3:]; block=[]; index+=1
            while index<len(lines) and not lines[index].strip().startswith('```'):
                block.append(lines[index]); index+=1
            story.append(Architecture() if language=='mermaid' else Paragraph('<br/>'.join(escape(s) for s in block),code))
            story.append(Spacer(1,8)); index+=1; continue
        if line.startswith('|'):
            rows=[]
            while index<len(lines) and lines[index].strip().startswith('|'):
                values=[v.strip() for v in lines[index].strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?',v) for v in values):
                    rows.append([Paragraph(inline(v,source),cell) for v in values])
                index+=1
            count=len(rows[0]); widths=([144,384] if count==2 else [122,203,203] if count==3 else [528/count]*count)
            table=Table(rows,colWidths=widths,repeatRows=1,hAlign='LEFT')
            table.setStyle(TableStyle([
                ('BACKGROUND',(0,0),(-1,0),PALE),('LINEBELOW',(0,0),(-1,0),1,TEAL),
                ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),
                ('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7),
                ('BOTTOMPADDING',(0,0),(-1,-1),7),('LINEBELOW',(0,1),(-1,-1),.35,LINE),
            ]))
            story.extend([table,Spacer(1,8)]); continue
        if line.startswith('# '):
            story.append(Paragraph(inline(line[2:],source),title))
        elif line.startswith('## '):
            story.append(Paragraph(inline(line[3:],source),h2))
        elif line.startswith('### '):
            story.append(Paragraph(inline(line[4:],source),h3))
        else:
            block=[line]; index+=1
            while index<len(lines) and lines[index].strip() and not lines[index].startswith(('#','|','```')):
                block.append(lines[index].strip()); index+=1
            story.append(Paragraph(inline(' '.join(block),source),body)); continue
        index+=1

    def frame(c,doc):
        c.setStrokeColor(TEAL); c.setLineWidth(2); c.line(42,760,570,760)
        c.setFont(FONT,7.4); c.setFillColor(GRAY)
        c.drawString(42,771,'ALPHAFORGE AI  /  POLYFINANCES 2026')
        c.drawString(42,22,'Investment research prototype. Historical evidence; no trading.')
        c.drawRightString(570,22,str(doc.page))
    doc=SimpleDocTemplate(str(output),pagesize=(612,792),rightMargin=42,leftMargin=42,topMargin=46,bottomMargin=38,
                          title='AlphaForge AI - '+name.replace('-',' ').title(),author='AlphaForge AI')
    doc.build(story,onFirstPage=frame,onLaterPages=frame)
    return output


if __name__=='__main__':
    for name,compact in [('one-pager',True),('technical-summary',False)]:
        print(render(name,compact))
