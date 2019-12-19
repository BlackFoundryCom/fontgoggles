from os import PathLike


def getOpener(fontPath: PathLike):
    openerKey = sniffFontType(fontPath)
    assert openerKey is not None
    numFontsFunc, openerFunc, getSortInfo = fontOpeners[openerKey]
    return numFontsFunc, openerFunc, getSortInfo


def sniffFontType(fontPath: PathLike):
    if not isinstance(fontPath, PathLike):
        raise TypeError("fontPath must be a Path(-like) object")
    openerKey = fontPath.suffix.lower().lstrip(".")
    if openerKey not in fontOpeners:
        return None
    return openerKey


def iterFontPathsAndNumbers(paths: list):
    for path in paths:
        if sniffFontType(path) is None and path.is_dir():
            for child in sorted(path.iterdir()):
                yield from iterFontNumbers(child)
        else:
            yield from iterFontNumbers(path)


def iterFontNumbers(path):
    if sniffFontType(path) is None:
        return
    numFonts, opener, getSortInfo = getOpener(path)
    for i in range(numFonts(path)):
        yield path, i


async def openOTF(fontPath: PathLike, fontNumber: int, fontData=None):
    from .baseFont import OTFFont
    if fontData is not None:
        font = OTFFont(fontData, fontNumber)
    else:
        font = OTFFont.fromPath(fontPath, fontNumber)
        fontData = font.fontData
    return (font, fontData)


async def openUFO(fontPath: PathLike, fontNumber: int, fontData=None):
    from .ufoFont import UFOFont
    assert fontData is None  # dummy
    font = UFOFont(fontPath)
    await font.load()
    return (font, None)


def numFontsOne(fontPath: PathLike):
    return 1


def numFontsTTC(fontPath: PathLike):
    from fontTools.ttLib.sfnt import readTTCHeader
    with open(fontPath, "rb") as f:
        header = readTTCHeader(f)
    return header.numFonts


def getSortInfoOTF(fontPath: PathLike, fontNum: int):
    # TODO: move to baseFont/otfFont
    from fontTools.ttLib import TTFont
    ttf = TTFont(fontPath, fontNumber=fontNum, lazy=True)
    sortInfo = {}
    name = ttf.get("name")
    os2 = ttf.get("OS/2")
    post = ttf.get("post")
    if name is not None:
        for key, nameIDs in [("familyName", [16, 1]), ("styleName", [17, 2])]:
            for nameID in nameIDs:
                nameRec = name.getName(nameID, 3, 1)
                if nameRec is not None:
                    sortInfo[key] = str(nameRec)
                    break
    if os2 is not None:
        sortInfo["weight"] = os2.usWeightClass
        sortInfo["width"] = os2.usWidthClass
    if post is not None:
        sortInfo["italicAngle"] = post.italicAngle
    return sortInfo


def getSortInfoUFO(fontPath: PathLike, fontNum: int):
    return {}


fontOpeners = {
    "ttf": (numFontsOne, openOTF, getSortInfoOTF),
    "otf": (numFontsOne, openOTF, getSortInfoOTF),
    "woff": (numFontsOne, openOTF, getSortInfoOTF),
    "woff2": (numFontsOne, openOTF, getSortInfoOTF),
    "ufo": (numFontsOne, openUFO, getSortInfoUFO),
    "ufos": (numFontsOne, openUFO, getSortInfoUFO),
    "ttc": (numFontsTTC, openOTF, getSortInfoOTF),
    "otc": (numFontsTTC, openOTF, getSortInfoOTF),
}

fileTypes = sorted(fontOpeners)
