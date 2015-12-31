
import random
import pyagg
import PIL, PIL.Image



class MapCanvas:
    def __init__(self, width, height, background=None, layers=None, *args, **kwargs):

        # remember and be remembered by the layergroup
        if not layers:
            layers = LayerGroup()
        self.layers = layers
        layers.connected_maps.append(self)

        # create the drawer with a default unprojected lat-long coordinate system
        self.drawer = pyagg.Canvas(width, height, background)
        self.drawer.geographic_space() 

        self.img = self.drawer.get_image()

    def pixel2coord(self, x, y):
        return self.drawer.pixel2coord(x, y)

    # Map canvas alterations

    def offset(self, xmove, ymove):
        self.drawer.move(xmove, ymove)

    def resize(self, width, height):
        self.drawer.resize(width, height, lock_ratio=True)
        self.img = self.drawer.get_image()

    # Zooming

    def zoom_bbox(self, xmin, ymin, xmax, ymax):
        self.drawer.zoom_bbox(xmin, ymin, xmax, ymax)

    def zoom_factor(self, factor, center=None):
        self.drawer.zoom_factor(factor, center=center)

    def zoom_units(self, units, center=None):
        self.drawer.zoom_units(units, center=center)

    # Drawing

    def render_one(self, layer):
        if layer.visible:
            layer.render(width=self.drawer.width,
                         height=self.drawer.height,
                         coordspace_bbox=self.drawer.coordspace_bbox)
            self.update_draworder()

    def render_all(self):
        for layer in self.layers:
            if layer.visible:
                layer.render(width=self.drawer.width,
                             height=self.drawer.height,
                             bbox=self.drawer.coordspace_bbox)
        self.update_draworder()

    def update_draworder(self):
        self.drawer.clear()
        for layer in self.layers:
            if layer.visible:
                self.drawer.paste(layer.img)
        self.img = self.drawer.get_image()

    def get_tkimage(self):
        # Special image format needed by Tkinter to display it in the GUI
        return self.drawer.get_tkimage()


        


class LayerGroup:
    def __init__(self):
        self.layers = list()
        self.connected_maps = list()

    def __iter__(self):
        for layer in self.layers:
            yield layer

    def add_layer(self, layer):
        self.layers.append(layer)

    def move_layer(self, from_pos, to_pos):
        layer = self.layers.pop(from_pos)
        self.layers.insert(to_pos, layer)

    def remove_layer(self, position):
        self.layers.pop(position)

    def get_position(self, layer):
        return self.layers.index(layer)




class VectorLayer:
    def __init__(self, data, **options):
        
        self.data = data
        self.visible = True
        self.img = None
        
        # by default, set random style color
        rand = random.randrange
        randomcolor = (rand(255), rand(255), rand(255), 255)
        self.styleoptions = {"fillcolor": randomcolor,
                             "sortorder": "incr"}
            
        # override default if any manually specified styleoptions
        self.styleoptions.update(options)

        # set up classifier
        features = self.data
        import classipy as cp
        for key,val in self.styleoptions.copy().items():
            if key in "fillcolor fillsize outlinecolor outlinewidth".split():
                if isinstance(val, dict):
                    # cache precalculated values in id dict
                    # more memory friendly alternative is to only calculate breakpoints
                    # and then find classvalue for feature when rendering,
                    # which is likely slower
                    classifier = cp.Classifier(features, **val)
                    self.styleoptions[key] = dict(classifier=classifier,
                                                   symbols=dict((id(f),classval) for f,classval in classifier)
                                                   )
                else:
                    self.styleoptions[key] = val

    def render(self, width, height, bbox=None):
        if not bbox:
            bbox = self.data.bbox
        
        drawer = pyagg.Canvas(width, height, background=None)
        drawer.custom_space(*bbox)

        # get features based on spatial index, for better speeds when zooming
        if not hasattr(self.data, "spindex"):
            self.data.create_spatial_index()
        features = self.data.quick_overlap(bbox)

        # custom draworder (sortorder is only used with sortkey)
        if "sortkey" in self.styleoptions:
            features = sorted(features, key=self.styleoptions["sortkey"],
                              reverse=self.styleoptions["sortorder"].lower() == "decr")

        # draw each as geojson
        for feat in features:
            
            # get symbols
            rendict = dict()
            for key in "fillcolor fillsize outlinecolor outlinewidth".split():
                if key in self.styleoptions:
                    val = self.styleoptions[key]
                    if isinstance(val, dict):
                        # lookup self in precomputed symboldict
                        rendict[key] = val["symbols"][id(feat)]
                    else:
                        rendict[key] = val

            # draw
            drawer.draw_geojson(feat.geometry, **rendict)
            
        self.img = drawer.get_image()



        
class RasterLayer:
    def __init__(self, data, **options):
        self.data = data
        self.visible = True
        self.img = None

        # by default, set random style color
        if not "type" in options:
            if len(data.bands) == 3:
                options["type"] = "rgb"
            else:
                options["type"] = "colorscale"

        if options["type"] == "grayscale":
            options["bandnum"] = options.get("bandnum", 0)
            band = self.data.bands[options["bandnum"]]
            
            # retrieve min and maxvals from data if not manually specified
            if not "minval" in options:
                options["minval"] = band.summarystats("min")["min"]
            if not "maxval" in options:
                options["maxval"] = band.summarystats("max")["max"]

        elif options["type"] == "colorscale":
            options["bandnum"] = options.get("bandnum", 0)
            band = self.data.bands[options["bandnum"]]
            
            # retrieve min and maxvals from data if not manually specified
            if not "minval" in options:
                options["minval"] = band.summarystats("min")["min"]
            if not "maxval" in options:
                options["maxval"] = band.summarystats("max")["max"]

            # set random gradient
            if not "gradcolors" in options:
                rand = random.randrange
                randomcolor = (rand(255), rand(255), rand(255), 255)
                randomcolor2 = (rand(255), rand(255), rand(255), 255)
                options["gradcolors"] = [randomcolor,randomcolor2]

        elif options["type"] == "rgb":
            options["r"] = options.get("r", 0)
            options["g"] = options.get("g", 1)
            options["b"] = options.get("b", 2)
            
        # remember style settings
        self.styleoptions = options

    def render(self, resampling="nearest", **georef):
        # NOT DONE...
        # position in space
        if "bbox" not in georef:
            georef["bbox"] = self.data.bbox
            
        rendered = self.data.resample(algorithm=resampling, **georef)

        if self.styleoptions["type"] == "grayscale":
            
            # Note: Maybe remove and instead must specify white and black in colorscale type...?
            # ...
            
            band = rendered.bands[self.styleoptions["bandnum"]]
            
            # equalize
            minval,maxval = self.styleoptions["minval"], self.styleoptions["maxval"]
            valrange = 1/float(maxval-minval) * 255
            expr = "(val - {minval}) * {valrange}".format(minval=minval,valrange=valrange)
            band.compute(expr)
            # colorize
            img = band.img.convert("LA")

        elif self.styleoptions["type"] == "colorscale":
            band = rendered.bands[self.styleoptions["bandnum"]]
            
            # equalize
            minval,maxval = self.styleoptions["minval"], self.styleoptions["maxval"]
            valrange = 1/float(maxval-minval) * 255
            expr = "(val - {minval}) * {valrange}".format(minval=minval,valrange=valrange)
            band.compute(expr)
            # colorize
            canv = pyagg.canvas.from_image(band.img.convert("RGBA"))
            canv = canv.color_remap(self.styleoptions["gradcolors"])
            img = canv.get_image()

        elif self.styleoptions["type"] == "rgb":
            rband = rendered.bands[self.styleoptions["r"]].img.convert("L")
            gband = rendered.bands[self.styleoptions["g"]].img.convert("L")
            bband = rendered.bands[self.styleoptions["b"]].img.convert("L")
            img = PIL.Image.merge("RGB", [rband,gband,bband])
            img = img.convert("RGBA")

        elif self.styleoptions["type"] == "3d surface":
            import matplotlib as mpl
            # ...
            pass

        # make edge and nodata mask transparent
        
        #blank = PIL.Image.new("RGBA", img.size, None)
        #blank.paste(img, mask=rendered.mask)
        #img = blank
        #r,g,b = img.split()[:3]
        #a = rendered.mask.convert("L")
        #rgba = (r,g,b,a)
        #img = PIL.Image.merge("RGBA", rgba)
        #img.putalpha(rendered.mask)
        #img.show()
        #rendered.mask.show()

        img.paste(0, mask=rendered.mask) # sets all bands to 0 incl the alpha band

        # final
        self.img = img


