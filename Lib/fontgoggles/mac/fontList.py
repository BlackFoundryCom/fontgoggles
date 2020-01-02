import AppKit
from vanilla import *
from fontTools.misc.arrayTools import offsetRect, scaleRect, unionRect
from fontgoggles.mac.drawing import *
from fontgoggles.mac.misc import textAlignments
from fontgoggles.misc.decorators import suppressAndLogException
from fontgoggles.misc.properties import delegateProperty, hookedProperty
from fontgoggles.misc.rectTree import RectTree


fontItemMinimumSize = 60
fontItemMaximumSize = 1500


class FGFontListView(AppKit.NSView):

    def acceptsFirstResponder(self):
        return True

    def becomeFirstResponder(self):
        return True

    def mouseDown_(self, event):
        self.vanillaWrapper().mouseDown(event)

    def keyDown_(self, event):
        self.vanillaWrapper().keyDown(event)

    def subscribeToMagnification_(self, scrollView):
        AppKit.NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(
            self, "_liveMagnifyWillStart:", AppKit.NSScrollViewWillStartLiveMagnifyNotification,
            scrollView)
        AppKit.NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(
            self, "_liveMagnifyDidEnd:", AppKit.NSScrollViewDidEndLiveMagnifyNotification,
            scrollView)

    _nestedZoom = 0

    @suppressAndLogException
    def _liveMagnifyWillStart_(self, notification):
        if self._nestedZoom == 0:
            self._savedClipBounds = self.superview().bounds()
            scrollView = notification.object()
            fontList = self.vanillaWrapper()
            minMag = (fontItemMinimumSize / fontList.itemSize)
            maxMag = (fontItemMaximumSize / fontList.itemSize)
            scrollView.setMinMagnification_(minMag)
            scrollView.setMaxMagnification_(maxMag)
        self._nestedZoom += 1

    @suppressAndLogException
    def _liveMagnifyDidEnd_(self, notification):
        self._nestedZoom -= 1
        if self._nestedZoom == 0:
            scrollView = notification.object()
            clipView = self.superview()

            finalBounds = clipView.bounds()
            x, y = finalBounds.origin
            dy = clipView.frame().size.height - clipView.bounds().size.height
            scrollX, scrollY = x, y - dy
            magnification = scrollView.magnification()
            scrollView.setMagnification_(1.0)

            fontList = self.vanillaWrapper()
            newItemSize = round(max(fontItemMinimumSize,
                                    min(fontItemMaximumSize, fontList.itemSize * magnification)))
            actualMag = newItemSize / fontList.itemSize
            fontList.resizeFontItems(newItemSize)
            newBounds = ((round(actualMag * scrollX), round(actualMag * scrollY)), self._savedClipBounds.size)
            scrollView.setMagnification_(1.0)
            newBounds = clipView.constrainBoundsRect_(newBounds)
            clipView.setBounds_(newBounds)
            scrollView.setMagnification_(1.0)
            self._savedClipBounds = None


arrowKeyDefs = {
    AppKit.NSUpArrowFunctionKey: (-1, 1),
    AppKit.NSDownArrowFunctionKey: (1, 1),
    AppKit.NSLeftArrowFunctionKey: (-1, 0),
    AppKit.NSRightArrowFunctionKey: (1, 0),
}

fontItemIdentifierTemplate = "fontItem_{index}"


class FontList(Group):

    nsViewClass = FGFontListView

    def __init__(self, fontKeys, width, itemSize, selectionChangedCallback=None,
                 glyphSelectionChangedCallback=None, arrowKeyCallback=None):
        super().__init__((0, 0, width, 900))
        self._fontItemIdentifiers = []
        self._selection = set()  # a set of fontItemIdentifiers
        self.vertical = 0  # 0, 1: it is also an index into (x, y) tuples
        self.itemSize = itemSize
        self.align = "left"
        self._selectionChangedCallback = selectionChangedCallback
        self._glyphSelectionChangedCallback = glyphSelectionChangedCallback
        self._arrowKeyCallback = arrowKeyCallback
        self._lastItemClicked = None
        self.setupFontItems(fontKeys)

    def _glyphSelectionChanged(self):
        if self._glyphSelectionChangedCallback is not None:
            self._glyphSelectionChangedCallback(self)

    def setupFontItems(self, fontKeys):
        # clear all subviews
        for attr, value in list(self.__dict__.items()):
            if isinstance(value, VanillaBaseObject):
                delattr(self, attr)
        self._fontItemIdentifiers = []
        itemSize = self.itemSize
        y = 0
        for index, fontKey in enumerate(fontKeys):
            fontItemIdentifier = fontItemIdentifierTemplate.format(index=index)
            fontItem = FontItem((0, y, 0, itemSize), fontKey, fontItemIdentifier)
            setattr(self, fontItemIdentifier, fontItem)
            self._fontItemIdentifiers.append(fontItemIdentifier)
            y += itemSize
        self.setPosSize((0, 0, self.width, y))

    @property
    def width(self):
        return self.getPosSize()[2]

    @width.setter
    def width(self, newWidth):
        x, y, w, h = self.getPosSize()
        self.setPosSize((x, y, newWidth, h))

    @property
    def height(self):
        return self.getPosSize()[3]

    @height.setter
    def height(self, newHeight):
        x, y, w, h = self.getPosSize()
        self.setPosSize((x, y, w, newHeight))

    @hookedProperty
    def align(self):
        # self.align has already been set to the new value
        for fontItem in self.iterFontItems():
            fontItem.align = self.align

        scrollView = self._nsObject.enclosingScrollView()
        if scrollView is None:
            return

        ourBounds = self._nsObject.bounds()
        clipView = scrollView.contentView()
        clipBounds = clipView.bounds()
        if clipBounds.size.width >= ourBounds.size.width:
            # Handled by AligningScrollView
            return

        sizeDiff = ourBounds.size.width - clipBounds.size.width
        atLeft = abs(clipBounds.origin.x) < 2
        atRight = abs(clipBounds.origin.x - sizeDiff) < 2
        atCenter = abs(clipBounds.origin.x - sizeDiff / 2) < 2
        if self.align == "left":
            if atRight or atCenter:
                clipBounds.origin.x = 0
        elif self.align == "center":
            if atLeft or atRight:
                clipBounds.origin.x = sizeDiff / 2
        elif self.align == "right":
            if atLeft or atCenter:
                clipBounds.origin.x = sizeDiff
        clipView.setBounds_(clipBounds)

    def iterFontItems(self):
        for fontItemIdentifier in self._fontItemIdentifiers:
            yield self.getFontItem(fontItemIdentifier)

    @hookedProperty
    def vertical(self):
        # Note that we heavily depend on hookedProperty's property that
        # the hook is only called when the value is different than before.
        vertical = self.vertical
        pos = [0, 0]
        for fontItem in self.iterFontItems():
            fontItem.vertical = vertical
            fontItem.fileNameLabel.setPosSize(fontItem.getFileNameLabelPosSize())
            fontItem.fileNameLabel.rotate([-90, 90][vertical])
            x, y, w, h = fontItem.getPosSize()
            w, h = h, w
            fontItem.setPosSize((*pos, w, h))
            pos[1 - vertical] += self.itemSize
        x, y, w, h = self.getPosSize()
        w, h = h, w
        self.setPosSize((x, y, w, h))
        self._nsObject.setNeedsDisplay_(True)

    @suppressAndLogException
    def resizeFontItems(self, itemSize):
        # XXX unused at the moment, but perhaps we'll come back it it
        scaleFactor = itemSize / self.itemSize
        self.itemSize = itemSize
        pos = [0, 0]
        for fontItem in self.iterFontItems():
            x, y, *wh = fontItem.getPosSize()
            wh[1 - self.vertical] = itemSize
            fontItem.setPosSize((*pos, *wh))
            pos[1 - self.vertical] += itemSize

        # calculate the center of our clip view in relative doc coords
        # so we can set the scroll position and zoom in/out "from the middle"
        x, y, w, h = self.getPosSize()
        clipView = self._nsObject.superview()
        (cx, cy), (cw, ch) = clipView.bounds()
        cx += cw / 2
        cy -= ch / 2
        cx /= w
        cy /= h

        if not self.vertical:
            self.setPosSize((x, y, w * scaleFactor, pos[1]))
            cx *= w * scaleFactor
            cy *= pos[1]
        else:
            self.setPosSize((x, y, pos[0], h * scaleFactor))
            cx *= pos[0]
            cy *= h * scaleFactor
        cx -= cw / 2
        cy += ch / 2
        clipBounds = clipView.bounds()
        clipBounds.origin = (cx, cy)
        clipView.setBounds_(clipBounds)

    @property
    def selection(self):
        return self._selection

    @selection.setter
    def selection(self, newSelection):
        diffSelection = self._selection ^ newSelection
        self._selection = newSelection
        for fontItemIdentifier in diffSelection:
            fontItem = self.getFontItem(fontItemIdentifier)
            fontItem.selected = not fontItem.selected
        if self._selectionChangedCallback is not None:
            self._selectionChangedCallback(self)

    def getFontItem(self, fontItemIdentifier):
        return getattr(self, fontItemIdentifier)

    def getNumFontItems(self):
        return len(self._fontItemIdentifiers)

    def getSingleSelectedItem(self):
        if len(self._fontItemIdentifiers) == 1:
            return self.getFontItem(self._fontItemIdentifiers[0])
        elif len(self.selection) == 1:
            return self.getFontItem(list(self.selection)[0])
        else:
            return None

    def _getSelectionRect(self, selection):
        selRect = None
        for fontItemIdentifier in selection:
            fontItem = self.getFontItem(fontItemIdentifier)
            if selRect is None:
                selRect = fontItem._nsObject.frame()
            else:
                selRect = AppKit.NSUnionRect(selRect, fontItem._nsObject.frame())
        return selRect

    def scrollSelectionToVisible(self, selection=None):
        if selection is None:
            selection = self._selection
        self._nsObject.scrollRectToVisible_(self._getSelectionRect(selection))

    def scrollGlyphSelectionToVisible(self):
        if self.selection:
            fontItems = (self.getFontItem(fii) for fii in self.selection)
        else:
            fontItems = (self.getFontItem(fii) for fii in self._fontItemIdentifiers)
        rects = []
        for fontItem in fontItems:
            view = fontItem.glyphLineView._nsObject
            x, y = fontItem._nsObject.frame().origin
            selRect = view.getSelectionRect()
            if selRect is not None:
                rects.append(AppKit.NSOffsetRect(selRect, x, y))
        if rects:
            selRect = rects[0]
            for rect in rects[1:]:
                selRect = AppKit.NSUnionRect(selRect, rect)
            self._nsObject.scrollRectToVisible_(selRect)

    @suppressAndLogException
    def mouseDown(self, event):
        glyphSelectionChanged = False
        fontItemIdentifier = self._lastItemClicked
        self._lastItemClicked = None
        if fontItemIdentifier is not None:
            fontItem = self.getFontItem(fontItemIdentifier)
            glyphSelectionChanged = bool(fontItem.popDiffSelection())
            clickedSelection = {fontItemIdentifier}
        else:
            for fontItem in self.iterFontItems():
                fontItem.selection = set()
            glyphSelectionChanged = True
            clickedSelection = set()

        if clickedSelection and event.modifierFlags() & AppKit.NSCommandKeyMask:
            newSelection = self._selection ^ clickedSelection
        elif fontItemIdentifier in self._selection:
            newSelection = None
        else:
            newSelection = clickedSelection
        if newSelection is not None:
            self.selection = newSelection
            if clickedSelection:
                self.scrollSelectionToVisible(clickedSelection)
        if glyphSelectionChanged:
            self._glyphSelectionChanged()

    @suppressAndLogException
    def keyDown(self, event):
        chars = event.characters()
        if chars in arrowKeyDefs:
            direction, vertical = arrowKeyDefs[chars]
            if vertical == self.vertical:
                if self._arrowKeyCallback is not None:
                    self._arrowKeyCallback(self, event)
                return

            if not self._selection:
                if direction == 1:
                    self.selection = {self._fontItemIdentifiers[0]}
                else:
                    self.selection = {self._fontItemIdentifiers[-1]}
            else:
                indices = [i for i, fii in enumerate(self._fontItemIdentifiers) if fii in self._selection]
                if direction == 1:
                    index = min(len(self._fontItemIdentifiers) - 1, indices[-1] + 1)
                else:
                    index = max(0, indices[0] - 1)
                if event.modifierFlags() & AppKit.NSShiftKeyMask:
                    self.selection = self.selection | {self._fontItemIdentifiers[index]}
                else:
                    self.selection = {self._fontItemIdentifiers[index]}
                self.scrollSelectionToVisible()


class FontItem(Group):

    vertical = delegateProperty("glyphLineView")
    selected = delegateProperty("glyphLineView")

    def __init__(self, posSize, fontKey, fontItemIdentifier):
        super().__init__(posSize)
        # self._nsObject.setWantsLayer_(True)
        # self._nsObject.setCanDrawSubviewsIntoLayer_(True)
        self.fontItemIdentifier = fontItemIdentifier
        self.glyphLineView = GlyphLine((0, 0, 0, 0))
        self.fileNameLabel = UnclickableTextBox(self.getFileNameLabelPosSize(), "", sizeStyle="small")
        self.progressSpinner = ProgressSpinner((10, 20, 25, 25))
        self.setFontKey(fontKey)

    def setIsLoading(self, isLoading):
        if isLoading:
            self.progressSpinner.start()
        else:
            self.progressSpinner.stop()

    def setFontKey(self, fontKey):
        fontPath, fontNumber = fontKey
        fileNameLabel = f"{fontPath.name}"
        if fontNumber or fontPath.suffix.lower() in {".ttc", ".otc"}:
            fileNameLabel += f"#{fontNumber}"
        self.fileNameLabel.set(fileNameLabel, tooltip=str(fontPath))

    @property
    def glyphs(self):
        return self.glyphLineView._nsObject._glyphs

    @glyphs.setter
    def glyphs(self, glyphs):
        self.glyphLineView._nsObject.glyphs = glyphs

    @property
    def selection(self):
        return self.glyphLineView._nsObject.selection

    @selection.setter
    def selection(self, newSelection):
        self.glyphLineView._nsObject.selection = newSelection

    def popDiffSelection(self):
        return self.glyphLineView._nsObject.popDiffSelection()

    @property
    def minimumExtent(self):
        return self.glyphLineView._nsObject.minimumExtent

    @property
    def align(self):
        return self.glyphLineView._nsObject.align

    @align.setter
    def align(self, value):
        if self.vertical:
            mapping = dict(top="left", center="center", bottom="right")
            value = mapping[value]
        self.fileNameLabel.align = value
        self.glyphLineView._nsObject.align = value

    def getFileNameLabelPosSize(self):
        if self.vertical:
            return (2, 10, 17, -10)
        else:
            return (10, 0, -10, 17)


class FGGlyphLineView(AppKit.NSView):

    def _scheduleRedraw(self):
        self.setNeedsDisplay_(True)

    selected = hookedProperty(_scheduleRedraw, default=False)
    align = hookedProperty(_scheduleRedraw, default="left")

    def init(self):
        self = super().init()
        self.vertical = 0  # 0, 1: it will also be an index into (x, y) tuples
        self._glyphs = None
        self._rectTree = None
        self._selection = set()
        self._hoveredGlyphIndex = None
        self._lastDiffSelection = None

        trackingArea = AppKit.NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
                self.bounds(),
                AppKit.NSTrackingActiveInKeyWindow | AppKit.NSTrackingMouseMoved |
                AppKit.NSTrackingMouseEnteredAndExited | AppKit.NSTrackingInVisibleRect,
                self, None)
        self.addTrackingArea_(trackingArea)

        return self

    def isOpaque(self):
        return True

    def acceptsFirstResponder(self):
        return True

    def acceptsFirstMouse(self):
        return True

    def becomeFirstResponder(self):
        # Defer to our FGFontListView
        fontListView = self.superview().superview()
        assert isinstance(fontListView, FGFontListView)
        return fontListView.becomeFirstResponder()

    @property
    def selection(self):
        return self._selection

    @selection.setter
    def selection(self, newSelection):
        diffSelection = self._selection ^ newSelection
        self._selection = newSelection
        for index in diffSelection:
            bounds = self.getGlyphBounds_(index)
            if bounds is not None:
                self.setNeedsDisplayInRect_(bounds)
        self._lastDiffSelection = diffSelection

    @property
    def hoveredGlyphIndex(self):
        return self._hoveredGlyphIndex

    @hoveredGlyphIndex.setter
    def hoveredGlyphIndex(self, index):
        hoveredGlyphIndex = self._hoveredGlyphIndex
        if index == hoveredGlyphIndex:
            return
        prevBounds = self.getGlyphBounds_(hoveredGlyphIndex)
        newBounds = self.getGlyphBounds_(index)
        if prevBounds is None:
            bounds = newBounds
        elif newBounds is None:
            bounds = prevBounds
        else:
            bounds = AppKit.NSUnionRect(prevBounds, newBounds)
        self._hoveredGlyphIndex = index
        if bounds is not None:
            self.setNeedsDisplayInRect_(bounds)

    def getGlyphBounds_(self, index):
        if index is None or index >= len(self._glyphs):
            return None
        bounds = self._glyphs[index].bounds
        if bounds is None:
            return None
        dx, dy = self.origin
        scaleFactor = self.scaleFactor
        bounds = offsetRect(scaleRect(bounds, scaleFactor, scaleFactor), dx, dy)
        return nsRectFromRect(bounds)

    def getSelectionRect(self):
        """This methods returns an NSRect suitable for scrollRectToVisible_.
        It uses the "advance box" of selected glyphs, not the bounding box.
        """
        scaleFactor = self.scaleFactor
        origin = self.origin
        extent = self.frame().size[1 - self.vertical]
        bounds = None
        for glyphIndex in self.selection:
            gi = self.glyphs[glyphIndex]
            pos = gi.pos[self.vertical] * scaleFactor + origin[self.vertical]
            adv = [gi.ax, gi.ay][self.vertical] * scaleFactor
            delta = [gi.dx, gi.dy][self.vertical] * scaleFactor
            if self.vertical:
                box = (0, pos - delta + adv, extent, pos - delta)
            else:
                box = (pos + delta, 0, pos + delta + adv, extent)
            if bounds is None:
                bounds = box
            else:
                bounds = unionRect(bounds, box)

        if bounds is None:
            return None
        dx, dy = self.origin
        return nsRectFromRect(bounds)

    def popDiffSelection(self):
        diffSelection = self._lastDiffSelection
        self._lastDiffSelection = None
        return diffSelection

    @property
    def glyphs(self):
        return self._glyphs

    @glyphs.setter
    def glyphs(self, glyphs):
        self._glyphs = glyphs
        rectIndexList = [(gi.bounds, index) for index, gi in enumerate(glyphs) if gi.bounds is not None]
        self._rectTree = RectTree.fromSeq(rectIndexList)
        self._selection = set()
        self._hoveredGlyphIndex = None  # no need to trigger smart redraw calculation
        self.setNeedsDisplay_(True)

    @property
    def minimumExtent(self):
        if self._glyphs is None:
            return self.margin * 2
        else:
            return self.margin * 2 + abs(self._glyphs.endPos[self.vertical]) * self.scaleFactor

    @property
    def scaleFactor(self):
        itemSize = self.frame().size[1 - self.vertical]
        return 0.7 * itemSize / self._glyphs.unitsPerEm

    @property
    def margin(self):
        itemSize = self.frame().size[1 - self.vertical]
        return 0.1 * itemSize

    @property
    def origin(self):
        endPos = abs(self._glyphs.endPos[self.vertical]) * self.scaleFactor
        margin = self.margin
        align = self.align
        itemExtent = self.frame().size[self.vertical]
        itemSize = self.frame().size[1 - self.vertical]
        if align == "right" or align == "bottom":
            pos = itemExtent - margin - endPos
        elif align == "center":
            pos = (itemExtent - endPos) / 2
        else:  # align == "left" or align == "top"
            pos = margin
        if not self.vertical:
            return pos, 0.25 * itemSize  # TODO: something with hhea/OS/2 ascender/descender
        else:
            return 0.5 * itemSize, itemExtent - pos  # TODO: something with vhea ascender/descender

    @suppressAndLogException
    def drawRect_(self, rect):
        backgroundColor = AppKit.NSColor.textBackgroundColor()
        foregroundColor = AppKit.NSColor.textColor()

        if self.selected:
            # Blend color could be a pref from the systemXxxxColor colors
            backgroundColor = backgroundColor.blendedColorWithFraction_ofColor_(
                0.5, AppKit.NSColor.selectedTextBackgroundColor())

        selection = self._selection
        hoveredGlyphIndex = self._hoveredGlyphIndex
        selectedColor = selectedSpaceColor = hoverColor = hoverSpaceColor = None
        if selection:
            selectedColor = foregroundColor.blendedColorWithFraction_ofColor_(
                0.9, AppKit.NSColor.systemRedColor())
            selectedSpaceColor = selectedColor.colorWithAlphaComponent_(0.2)
        if hoveredGlyphIndex is not None:
            hoverColor = AppKit.NSColor.systemBlueColor()
            if hoveredGlyphIndex in selection:
                hoverColor = hoverColor.blendedColorWithFraction_ofColor_(
                    0.5, selectedColor)
            hoverSpaceColor = hoverColor.colorWithAlphaComponent_(0.2)

        colors = {
            # (empty, selected, hovered)
            (0, 0, 0): foregroundColor,
            (0, 0, 1): hoverColor,
            (0, 1, 0): selectedColor,
            (0, 1, 1): hoverColor,
            (1, 0, 0): None,
            (1, 0, 1): hoverSpaceColor,
            (1, 1, 0): selectedSpaceColor,
            (1, 1, 1): hoverSpaceColor,
        }

        backgroundColor.set()
        AppKit.NSRectFill(rect)

        if not self._glyphs:
            return

        dx, dy = self.origin

        invScale = 1 / self.scaleFactor
        rect = rectFromNSRect(rect)
        rect = scaleRect(offsetRect(rect, -dx, -dy), invScale, invScale)

        translate(dx, dy)
        scale(self.scaleFactor)

        foregroundColor.set()
        lastPosX = lastPosY = 0
        for index in self._rectTree.iterIntersections(rect):
            gi = self._glyphs[index]
            selected = index in selection
            hovered = index == hoveredGlyphIndex
            empty = not gi.path.elementCount()
            posX, posY = gi.pos
            translate(posX - lastPosX, posY - lastPosY)
            lastPosX, lastPosY = posX, posY
            color = colors[empty, selected, hovered]
            if color is None:
                continue
            color.set()
            if empty:
                AppKit.NSRectFillUsingOperation(nsRectFromRect(offsetRect(gi.bounds, -posX, -posY)),
                                                AppKit.NSCompositeSourceOver)
            else:
                gi.path.fill()

    def mouseMoved_(self, event):
        point = self.convertPoint_fromView_(event.locationInWindow(), None)
        self.hoveredGlyphIndex = self.findGlyph_(self.convertPoint_fromView_(event.locationInWindow(), None))

    def mouseEntered_(self, event):
        self.mouseMoved_(event)

    def mouseExited_(self, event):
        self.hoveredGlyphIndex = None

    @suppressAndLogException
    def mouseDown_(self, event):
        index = self.findGlyph_(self.convertPoint_fromView_(event.locationInWindow(), None))

        if not event.modifierFlags() & AppKit.NSCommandKeyMask:
            if index is None:
                newSelection = set()
            elif index in self.selection:
                newSelection = self.selection
            else:
                newSelection = {index}
            self.selection = newSelection

        # tell our parent we've been clicked on
        fontItemIdentifier = self.superview().vanillaWrapper().fontItemIdentifier
        fontList = self.superview().superview().vanillaWrapper()
        fontList._lastItemClicked = fontItemIdentifier
        super().mouseDown_(event)

    def findGlyph_(self, point):
        if self._rectTree is None:
            return None

        x, y = point
        scaleFactor = self.scaleFactor
        dx, dy = self.origin
        x -= dx
        y -= dy
        x /= scaleFactor
        y /= scaleFactor

        indices = list(self._rectTree.iterIntersections((x, y, x, y)))
        if not indices:
            index = None
        elif len(indices) == 1:
            index = indices[0]
        else:
            # There are multiple candidates. Let's do point-inside testing,
            # and take the last hit, if any. Fall back to the last.
            for index in reversed(indices):
                gi = self._glyphs[index]
                posX, posY = gi.pos
                if gi.path.containsPoint_((x - posX, y - posY)):
                    break
            else:
                index = indices[-1]
        return index


class GlyphLine(Group):
    nsViewClass = FGGlyphLineView
    vertical = delegateProperty("_nsObject")
    selected = delegateProperty("_nsObject")


class FGUnclickableTextField(AppKit.NSTextField):

    def hitTest_(self, point):
        return None


class UnclickableTextBox(TextBox):

    """This TextBox sublass is transparent for clicks."""

    nsTextFieldClass = FGUnclickableTextField

    def __init__(self, *args, fontSize=12, **kwargs):
        super().__init__(*args, **kwargs)
        self._nsObject.cell().setLineBreakMode_(AppKit.NSLineBreakByTruncatingMiddle)

    def set(self, value, tooltip=None):
        super().set(value)
        if tooltip is not None:
            self._nsObject.setToolTip_(tooltip)

    def rotate(self, angle):
        self._nsObject.rotateByAngle_(angle)

    @property
    def align(self):
        return self._nsObject.alignment()

    @align.setter
    def align(self, value):
        nsAlignment = textAlignments.get(value, textAlignments["left"])
        self._nsObject.cell().setAlignment_(nsAlignment)
