
import itertools, operator, math
from .data import *

import shapely, shapely.ops, shapely.geometry
from shapely.prepared import prep as supershapely






# Select extract operations

def crop(data, bbox):
    """
    Crops the data by a bounding box.
    Used for quickly focusing data on a subregion.
    """
    
    # create spatial index
    if not hasattr(data, "spindex"): data.create_spatial_index()

    out = VectorData()
    out.fields = list(data.fields)

    bboxgeom = shapely.geometry.box(*bbox)
    iterable = ((feat,feat.get_shapely()) for feat in data.quick_overlap(bbox))
    for feat,geom in iterable:
        intsec = geom.intersection(bboxgeom)
        if not intsec.is_empty:
            out.add_feature(feat.row, intsec.__geo_interface__)

    return out

def tiled(data, tilesize=None, tiles=(5,5)):
    width = abs(data.bbox[2] - data.bbox[0])
    height = abs(data.bbox[3] - data.bbox[1])
    
    if tilesize:
        tw,th = tilesize

    elif tiles:
        tw,th = width / float(tiles[0]), height / float(tiles[1])

    startx,starty,stopx,stopy = data.bbox

    def _floatrange(fromval,toval,step):
        "handles both ints and flots"
        # NOTE: maybe not necessary to test low-high/high-low
        # since vector bbox is always min-max
        val = fromval
        if fromval < toval:
            while val <= toval:
                yield val, val+step
                val += step
        else:
            while val >= toval:
                yield val, val-step
                val -= step
    
    for y1,y2 in _floatrange(starty, stopy, th):
        y2 = y2 if y2 <= stopy else stopy # cap
        for x1,x2 in _floatrange(startx, stopx, tw):
            x2 = x2 if x2 <= stopx else stopx # cap
            tile = crop(data, [x1,y1,x2,y2])
            if len(tile) > 0:
                yield tile

def where(data, other, condition, **kwargs):
    """
    Locates and returns those features that match some spatial condition
    with another dataset.

    I.e. "spatial select", "select by location". 
    """
    # TODO: Maybe should only be "join" and "where"...
    
    # TODO: Maybe rename "select_where"
    # TODO: Maybe simply add optional "where" option to the basic "select" method,
    # passed as list of data-condition tuples (allowing comparing to multiple layers)
    # The conditions can be defined as separate functions in this module comparing two
    # datas:
    # ie distance, intersects, within, contains, crosses, touches, equals, disjoint. 
    
    # same as select by location
    condition = condition.lower()
    
    # create spatial index
    if not hasattr(data, "spindex"): data.create_spatial_index()
    if not hasattr(other, "spindex"): other.create_spatial_index()

    out = VectorData()
    out.fields = list(data.fields)

    if condition in ("distance",):
        maxdist = kwargs.get("radius")
        if not maxdist:
            raise Exception("The 'distance' select condition requires a 'radius' arg")

        for feat in data:
            geom = feat.get_shapely()
            
            for otherfeat in other:
                othergeom = otherfeat.get_shapely()
                
                if geom.distance(othergeom) <= maxdist:
                    out.add_feature(feat.row, feat.geometry)
                    break  # only one match is needed

        return out

    elif condition in ("intersects", "within", "contains", "crosses", "touches", "equals"):
        for feat in data.quick_overlap(other.bbox):
            geom = feat.get_shapely()
            matchtest = getattr(geom, condition)
            
            for otherfeat in other.quick_overlap(feat.bbox):
                othergeom = otherfeat.get_shapely()
                
                if matchtest(othergeom):
                    out.add_feature(feat.row, feat.geometry)
                    break  # only one match is needed

        return out

    elif condition in ("disjoint",):
        # first add those whose bboxes clearly dont overlap
        for feat in data.quick_disjoint(other.bbox):
            out.add_feature(feat.row, feat.geometry)

        # then check those that might overlap
        for feat in data.quick_overlap(other.bbox):
            geom = feat.get_shapely()

            # has to be disjoint with all those that maybe overlap,
            # ie a feature that intersects at least one feature in the
            # other layer is not disjoint
            disjoint = all((otherfeat.get_shapely().disjoint(geom) for otherfeat in other.quick_overlap(feat.bbox)))

            if disjoint:
                out.add_feature(feat.row, feat.geometry)

        return out
    
    else:
        raise Exception("Unknown select condition")








# File management

def split(data, key, breaks="unique", **kwargs):
    """
    Splits a vector data layer into multiple ones based on a key which can be
    a field name, a list of field names, or a function. The default is to
    create a split for each new unique occurance of the key value, but the
    breaks arg can also be set to the name of other classification algorithms
    or to a list of your own custom break values. The key, breaks, and kwargs
    follow the input and behavior of the Classipy package's split and unique
    functions. 

    Iterates through each new split layer one at a time. 
    """
    
    # TODO: MAYBE SWITCH key TO by
    
    keywrap = key
    if not hasattr(key, "__call__"):
        if isinstance(key,(list,tuple)):
            keywrap = lambda f: tuple((f[k] for k in key))
        else:
            keywrap = lambda f: f[key]

    import classipy as cp
    if breaks == "unique":
        grouped = cp.unique(data, key=keywrap, **kwargs)
    else:
        grouped = cp.split(data, breaks=breaks, key=keywrap, **kwargs)
        
    for splitid,features in grouped:
        outfile = VectorData()
        outfile.fields = list(data.fields)
        for oldfeat in features:
            outfile.add_feature(oldfeat.row, oldfeat.geometry)
        yield splitid,outfile

def merge(*datalist):
    """
    Merges two or more vector data layers, combining all their rows
    and fields into a single table.

    Adds the merged data to the layers list.
    """
    #make empty table
    firstfile = datalist[0]
    outfile = VectorData()
    #combine fields from all files
    outfields = list(firstfile.fields)
    for data in datalist[1:]:
        for field in data.fields:
            if field not in outfields:
                outfields.append(field)
    outfile.fields = outfields
    #add the rest of the files
    for data in datalist:
        for feature in data:
            geometry = feature.geometry.copy() if feature.geometry else None
            row = []
            for field in outfile.fields:
                if field in data.fields:
                    row.append( feature[field] )
                else:
                    row.append( "" )
            outfile.add_feature(row, geometry)
    #return merged file
    return outfile







# Polishing

def clean(data, tolerance=0, preserve_topology=True):
    """Cleans the vector data of unnecessary clutter such as repeat
    points or closely related points within the distance specified in the
    'tolerance' parameter. Also tries to fix any broken geometries, dropping
    any unfixable ones.

    Adds the resulting cleaned data to the layers list.
    """    
    # create new file
    outfile = VectorData()
    outfile.fields = list(data.fields)

    # clean
    for feat in data:
        shapelyobj = feat.get_shapely()
        
        # try fixing invalid geoms
        if not shapelyobj.is_valid:
            if "Polygon" in shapelyobj.type:
                # fix bowtie polygons
                shapelyobj = shapelyobj.buffer(0.0)

        # remove repeat points (tolerance=0)
        # (and optionally smooth out complex shapes, tolerance > 0)
        shapelyobj = shapelyobj.simplify(tolerance, preserve_topology=preserve_topology)
            
        # if still invalid, do not add to output
        if not shapelyobj.is_valid:
            continue

        # write to file
        geojson = shapelyobj.__geo_interface__
        outfile.add_feature(feat.row, geojson)

    return outfile

##def selfoverlap(data, primkey):
##    """Clean away any internal overlap of features,
##    using primkey to decide which feature to keep"""
##    # predefined method that performs a common series of operations for
##    # dealing with selfoverlaps, eg get selfintersections then aggregate by duplicates geometries
##    # or get selfintersections then choose one based on priority key
##    # ...
##
##    raise Exception("Not yet implemented")

def snap(data, otherdata, tolerance=0.0000001):
    """Snaps all vertexes from the features in one layer snap to the vertexes of features in another layer within a certain distance"""
    
    # default should be 0.001 meters (1 millimeter), ala ArcGIS
    # should be calculated based on crs

    # TODO: for now just keeps snapping, should only snap to closest parts...

    if not hasattr(otherdata, "spindex"):
        otherdata.create_spatial_index()

    from shapely.ops import snap as _snap

    out = data.copy()
    for feat in out:
        shp = feat.get_shapely()
        buff = shp.buffer(tolerance)
        for otherfeat in otherdata.quick_overlap(buff.bounds):
            othershp = otherfeat.get_shapely()
            if buff.intersects(othershp):
                print "snap"
                shp = _snap(shp, othershp, tolerance)
        feat.geometry = shp.__geo_interface__
        
    return out






# Create operations

def connect(frompoints, topoints, key=None, greatcircle=True, segments=100):
    """Two point files, and for each frompoint draw line to each topoint
    that matches based on some key value."""

    # get key
    if isinstance(key, (list,tuple)) and len(key) == 2:
        k1,k2 = key
    else:
        k1 = k2 = key # same key for both
    key1 = k1 if hasattr(k1,"__call__") else lambda f:f[k1]
    key2 = k2 if hasattr(k2,"__call__") else lambda f:f[k2]

    from ._helpers import great_circle_path

    # TODO: allow any geometry types via centroids, not just point types
    # ...

    # TODO: optimize with hash lookup table
    # ...
        
    def flatten(data):
        for feat in data:
            if not feat.geometry: continue
            geotype = feat.geometry["type"]
            coords = feat.geometry["coordinates"]
            if "Multi" in geotype:
                for singlepart in coords:
                    geoj = {"type": geotype.replace("Multi", ""),
                            "coordinates": singlepart}
                    yield feat, geoj
            else:
                yield feat, feat.geometry

    # create new file
    outfile = VectorData()
    outfile.fields = list(frompoints.fields)
    outfile.fields.extend(topoints.fields)

    # connect points matching criteria
    for fromfeat,frompoint in flatten(frompoints):
        for tofeat,topoint in flatten(topoints):
            match = key1(fromfeat) == key2(tofeat) if key1 and key2 else True
            if match:
                if greatcircle:
                    linepath = great_circle_path(frompoint["coordinates"], topoint["coordinates"], segments=segments)
                else:
                    linepath = [frompoint["coordinates"], topoint["coordinates"]]
                geoj = {"type": "LineString",
                        "coordinates": linepath}
                row = list(fromfeat.row)
                row.extend(tofeat.row)
                outfile.add_feature(row=row, geometry=geoj)

    return outfile






# Modify operations

def buffer(data, dist, join_style="round", cap_style="round", mitre_limit=1.0, geodetic=False):
    """
    Buffering the data by a positive distance grows the geometry,
    while a negative distance shrinks it. Distance units should be given in
    units of the data's coordinate reference system. 

    Distance is an expression written in Python syntax, where it is possible
    to access the attributes of each feature by writing: feat['fieldname'].
    """
    # get distance func
    if hasattr(dist, "__call__"):
        distfunc = dist
    else:
        distfunc = lambda f: dist 

    # get buffer func
    if geodetic:
        # geodetic
        if data.type != "Point":
            raise Exception("Geodetic buffer only implemented for points")

        from ._helpers import geodetic_buffer
        def bufferfunc(feat):
            geoj = feat.geometry
            distval = distfunc(feat)
            return geodetic_buffer(geoj, distval, resolution)

    else:
        # geometry
        joincode = {"round":1,
                    "flat":2,
                    "square":3}[join_style]
        capcode = {"round":1,
                    "mitre":2,
                    "bevel":3}[cap_style]
        def bufferfunc(feat):
            geom = feat.get_shapely()
            distval = distfunc(feat)
            buffered = geom.buffer(distval, join_style=joincode, cap_style=capcode, mitre_limit=mitre_limit)
            return buffered.__geo_interface__
        
    # buffer and change each geojson dict in-place
    new = VectorData()
    new.fields = list(data.fields)
    for feat in data:
        buffered = bufferfunc(feat)
        new.add_feature(feat.row, buffered)
        
    # change data type to polygon
    new.type = "Polygon"
    return new

def cut(data, cutter):
    """
    Cuts apart a layer by the lines of another layer
    """

    # TODO: not sure if correct yet
    # NOTE: requires newest version of shapely

    from shapely.ops import split as _split

    outdata = VectorData()
    outdata.fields = list(data.fields)

    # point data cannot be cut or used for cutting
    if "Point" in data.type or "Point" in cutter.type:
        raise Exception("Point data cannot be cut or used for cutting, only polygons or lines")

    # create spatial index
    if not hasattr(data, "spindex"): data.create_spatial_index()
    if not hasattr(cutter, "spindex"): cutter.create_spatial_index()

    # cut
    for feat in data.quick_overlap(cutter.bbox):
        geom = feat.get_shapely()

        cutgeoms = (cutfeat.get_shapely() for cutfeat in cutter.quick_overlap(feat.bbox))
        cutgeoms = (cutgeom for cutgeom in cutgeoms if cutgeom.intersects(geom))
        def flat(g):
            if hasattr(g, "geoms"):
                return g.geoms
            else:
                return [g]
        cutgeom = shapely.geom.MultiPolygon(sum((flat(g) for g in cutgeoms)))
        newgeom = _split(geom, cutgeom)

        # add feature
        outdata.add_feature(feat.row, newgeom.__geo_interface__)
        
    return outdata

def reproject(data, fromcrs, tocrs):
    """Reprojects from one crs to another"""
    import pyproj

    def _project(points):
        xs,ys = itertools.izip(*points)
        xs,ys = pyproj.transform(pyproj.Proj(fromcrs),
                                    pyproj.Proj(tocrs),
                                    xs, ys)
        newpoints = list(itertools.izip(xs, ys))
        return newpoints

    out = data.copy()
    
    for feat in out:
        feat.transform(_project)

    return out



