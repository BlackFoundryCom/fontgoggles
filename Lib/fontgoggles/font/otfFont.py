import io
from fontTools.ttLib import TTFont
from .baseFont import BaseFont
from .glyphDrawing import GlyphDrawing
from ..compile.compilerPool import compileTTXToBytes
from ..misc.ftFont import FTFont
from ..misc.hbShape import HBShape
from ..misc.properties import cachedProperty


class _OTFBaseFont(BaseFont):

    def _getGlyphDrawing(self, glyphName, colorLayers):
        if "VarC" in self.ttFont:
            from fontTools.pens.cocoaPen import CocoaPen
            pen = CocoaPen(None)
            location = self._currentVarLocation or {}
            self._varcFont.drawGlyph(pen, glyphName, location)
            return GlyphDrawing([(pen.path, None)])
        if colorLayers and "COLR" in self.ttFont:
            colorLayers = self.ttFont["COLR"].ColorLayers
            layers = colorLayers.get(glyphName)
            if layers is not None:
                drawingLayers = [(self.ftFont.getOutlinePath(layer.name), layer.colorID)
                                 for layer in layers]
                return GlyphDrawing(drawingLayers)
        outline = self.ftFont.getOutlinePath(glyphName)
        return GlyphDrawing([(outline, None)])

    @cachedProperty
    def _varcFont(self):
        from fontTools.ttLib import registerCustomTableClass
        from rcjktools.ttVarCFont import TTVarCFont
        registerCustomTableClass("VarC", "rcjktools.table_VarC", "table_VarC")
        return TTVarCFont(None, ttFont=self.ttFont, hbFont=self.shaper.font)

    def varLocationChanged(self, varLocation):
        self.ftFont.setVarLocation(varLocation if varLocation else {})

    @cachedProperty
    def colorPalettes(self):
        if "CPAL" in self.ttFont:
            palettes = []
            for paletteRaw in self.ttFont["CPAL"].palettes:
                palette = [(color.red/255, color.green/255, color.blue/255, color.alpha/255)
                           for color in paletteRaw]
                palettes.append(palette)
            return palettes
        else:
            return None


class OTFFont(_OTFBaseFont):

    def __init__(self, fontPath, fontNumber, dataProvider=None):
        super().__init__(fontPath, fontNumber)
        if dataProvider is not None:
            # This allows us for TTC fonts to share their raw data
            self.fontData = dataProvider.getData(fontPath)
        else:
            with open(fontPath, "rb") as f:
                self.fontData = f.read()

    async def load(self, outputWriter):
        fontData = self.fontData
        f = io.BytesIO(fontData)
        self.ttFont = TTFont(f, fontNumber=self.fontNumber, lazy=True)
        if self.ttFont.flavor in ("woff", "woff2"):
            self.ttFont.flavor = None
            self.ttFont.recalcBBoxes = False
            self.ttFont.recalcTimestamp = False
            f = io.BytesIO()
            self.ttFont.save(f, reorderTables=False)
            fontData = f.getvalue()
        self.ftFont = FTFont(fontData, fontNumber=self.fontNumber, ttFont=self.ttFont)
        self.shaper = HBShape(fontData, fontNumber=self.fontNumber, ttFont=self.ttFont)


class TTXFont(_OTFBaseFont):

    async def load(self, outputWriter):
        fontData = await compileTTXToBytes(self.fontPath, outputWriter)
        f = io.BytesIO(fontData)
        self.ttFont = TTFont(f, fontNumber=self.fontNumber, lazy=True)
        self.ftFont = FTFont(fontData, fontNumber=self.fontNumber, ttFont=self.ttFont)
        self.shaper = HBShape(fontData, fontNumber=self.fontNumber, ttFont=self.ttFont)
