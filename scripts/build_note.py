"""Render the research note from Markdown and the included figures."""
import argparse
import html
import io
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

def pdf_from_markdown(text, path, work_dir):
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import mathtext, get_data_path
    from matplotlib.font_manager import FontProperties
    from pypdf import PdfReader, PdfWriter, Transformation
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak, Flowable
    from PIL import Image as PILImage
    fonts=Path(get_data_path())/'fonts/ttf'
    for name,file in [('Body','DejaVuSerif.ttf'),('BodyBold','DejaVuSerif-Bold.ttf'),('BodyItalic','DejaVuSerif-Italic.ttf'),
                      ('Sans','DejaVuSans.ttf'),('SansBold','DejaVuSans-Bold.ttf'),('Mono','DejaVuSansMono.ttf')]:
        pdfmetrics.registerFont(TTFont(name,str(fonts/file)))
    pdfmetrics.registerFontFamily('Body',normal='Body',bold='BodyBold',italic='BodyItalic',boldItalic='BodyBold')
    pdfmetrics.registerFontFamily('Sans',normal='Sans',bold='SansBold',italic='Sans',boldItalic='SansBold')
    ink=colors.HexColor('#172d40');muted=colors.HexColor('#586776');accent=colors.HexColor('#b84b61')
    styles={
        'body':ParagraphStyle('body',fontName='Body',fontSize=10.2,leading=14.1,spaceAfter=7,textColor=ink),
        'title':ParagraphStyle('title',fontName='SansBold',fontSize=24,leading=28,spaceAfter=11,textColor=ink),
        'h2':ParagraphStyle('h2',fontName='SansBold',fontSize=15,leading=19,spaceBefore=8,spaceAfter=9,textColor=ink,keepWithNext=True),
        'h3':ParagraphStyle('h3',fontName='SansBold',fontSize=10.3,leading=14,spaceBefore=6,spaceAfter=5,textColor=ink,keepWithNext=True),
        'caption':ParagraphStyle('caption',fontName='Sans',fontSize=7.8,leading=10.3,spaceAfter=9,textColor=muted),
        'cell':ParagraphStyle('cell',fontName='Sans',fontSize=7.7,leading=10,alignment=TA_LEFT,textColor=ink),
        'reference':ParagraphStyle('reference',fontName='Sans',fontSize=7.7,leading=10.2,spaceAfter=5,textColor=ink)}
    def inline(s):
        s=html.escape(s,quote=False)
        s=re.sub(r'\*\*(.*?)\*\*',r'<b>\1</b>',s)
        s=re.sub(r'`([^`]+)`',r'<font name="Mono" size="7.4">\1</font>',s)
        s=re.sub(r'\[([^\]]+)\]\((https?://[^)]+)\)',r'<link href="\2" color="#365f7b">\1</link>',s)
        s=re.sub(r'\[([^\]]+)\]\((?!https?://)[^)]+\)', r'\1', s)
        return s
    width=A4[0]-92
    equation_placements=[]
    equation_dir=work_dir/'PDF'
    equation_dir.mkdir(parents=True, exist_ok=True)

    class Equation(Flowable):
        """Reserve layout space for a vector equation and record its position."""
        def __init__(self, source):
            super().__init__()
            self.source=source
            box=PdfReader(str(source)).pages[0].mediabox
            self.scale=min(1.,width/float(box.width))
            self.width=float(box.width)*self.scale
            self.height=float(box.height)*self.scale
            self.hAlign='CENTER'

        def draw(self):
            x,y=self.canv.absolutePosition(0,0)
            equation_placements.append((self.canv.getPageNumber()-1,self.source,self.scale,x,y))

    parts=text.split('<!-- page -->')
    if len(parts)!=6: raise ValueError('The note must contain six explicit sections/pages')
    story=[];equation=0
    for page,part in enumerate(parts):
        lines=part.strip().splitlines();i=0
        if page: story.append(PageBreak())
        while i<len(lines):
            line=lines[i].strip();i+=1
            if not line: continue
            if line=='$$':
                terms=[]
                while i<len(lines) and lines[i].strip()!='$$':terms.append(lines[i].strip());i+=1
                i+=1;equation+=1
                output=equation_dir/f'equation_{equation}.pdf'
                display_math=''.join(terms).replace(r'\frac{',r'\dfrac{')
                with matplotlib.rc_context({'mathtext.fontset':'cm','pdf.fonttype':42}):
                    mathtext.math_to_image('$'+display_math+'$',str(output),format='pdf',
                                          prop=FontProperties(size=12,math_fontfamily='cm'))
                story += [Spacer(1,5),Equation(output),Spacer(1,11)]
            elif line.startswith('!['):
                image_path=re.match(r'!\[.*?\]\((.*?)\)',line).group(1)
                source=ROOT/'reports'/image_path
                with PILImage.open(source) as im:iw,ih=im.size
                w=min(width,282*iw/ih);h=w*ih/iw
                story.extend([Image(str(source),width=w,height=h),Spacer(1,7)])
            elif line.startswith('|'):
                table=[line]
                while i<len(lines) and lines[i].strip().startswith('|'):table.append(lines[i].strip());i+=1
                parsed=[[c.strip() for c in row.strip('|').split('|')] for row in table]
                parsed=[row for row in parsed if not all(re.fullmatch(r'[-: ]+',c) for c in row)]
                n=len(parsed[0]);widths=([.40,.30,.30] if n==3 else [.29,.25,.32,.14])
                if 'Scenario' in parsed[0]:widths=[.24,.30,.32,.14]
                data=[[Paragraph(inline(c),styles['cell']) for c in row] for row in parsed]
                tab=Table(data,colWidths=[width*v for v in widths],hAlign='LEFT')
                tab.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8eef2')),
                    ('LINEBELOW',(0,0),(-1,0),.8,ink),('LINEBELOW',(0,-1),(-1,-1),.6,ink),
                    ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f6f8f9')]),
                    ('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),6),
                    ('BOTTOMPADDING',(0,0),(-1,-1),6),('LEFTPADDING',(0,0),(-1,-1),7),
                    ('RIGHTPADDING',(0,0),(-1,-1),7)]))
                story += [tab,Spacer(1,7)]
            elif line.startswith('# '):story.append(Paragraph(inline(line[2:]),styles['title']))
            elif line.startswith('## '):story.append(Paragraph(inline(line[3:]),styles['h2']))
            elif line.startswith('### '):story.append(Paragraph(inline(line[4:]),styles['h3']))
            else:
                paragraph=[line]
                while i<len(lines) and lines[i].strip() and not lines[i].startswith(('#','|','![','$$')):
                    paragraph.append(lines[i].strip());i+=1
                s=' '.join(paragraph)
                style='caption' if s.startswith(('Table ','Figure ')) else ('reference' if re.match(r'\[[1-4]\]',s) else 'body')
                story.append(Paragraph(inline(s),styles[style]))
    def furniture(canvas,doc):
        canvas.saveState();canvas.setStrokeColor(accent);canvas.setLineWidth(1)
        canvas.line(46,A4[1]-33,A4[0]-46,A4[1]-33)
        canvas.setFont('Sans',7);canvas.setFillColor(muted)
        canvas.drawString(46,26,'JAY (SHIJIE) JIANG  |  FORECAST-RISK TOLERANCE')
        canvas.drawRightString(A4[0]-46,26,f'{doc.page} / 6')
        canvas.restoreState()
    doc=SimpleDocTemplate(str(path),pagesize=A4,rightMargin=46,leftMargin=46,topMargin=43,bottomMargin=43,
                          title='Forecast-Risk Tolerance and Portfolio Rebalancing',author='Jay (Shijie) Jiang')
    doc.build(story,onFirstPage=furniture,onLaterPages=furniture)
    # Overlay the embedded-font equation pages at their reserved coordinates.
    # Build the output in memory before replacing the normal PDF path.
    writer=PdfWriter()
    writer.clone_document_from_reader(PdfReader(str(path)))
    for page_number,source,scale,x,y in equation_placements:
        equation_page=PdfReader(str(source)).pages[0]
        writer.pages[page_number].merge_transformed_page(
            equation_page,Transformation().scale(scale).translate(x,y))
    buffer=io.BytesIO()
    writer.write(buffer)
    path.write_bytes(buffer.getvalue())
    pdf=PdfReader(str(path))
    if len(pdf.pages)!=6:raise ValueError(f'Note overflows: {len(pdf.pages)} pages instead of six')
    if any('{{' in (p.extract_text() or '') for p in pdf.pages):raise ValueError('PDF contains unresolved tokens')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, default=ROOT/'work/note')
    args = parser.parse_args()
    args.work_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault('MPLCONFIGDIR', str(args.work_dir/'matplotlib'))
    text = (ROOT/'reports/research_note.md').read_text(encoding='utf-8')
    # Normalize typography for consistent PDF font coverage.
    text = text.translate(str.maketrans({'–':'-', '—':'-', '‑':'-'}))
    destination = ROOT/'PDF/research_note.pdf'
    pdf_from_markdown(text, destination, args.work_dir)
    print(destination)


if __name__ == '__main__':
    main()
