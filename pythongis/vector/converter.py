
import itertools, operator, math
from .data import *

import shapely, shapely.ops, shapely.geometry
from shapely.prepared import prep as supershapely



# Common helper functions 

def _to_multicentroids(data):
    """create multiple centroid points for each multi geometry part"""
    
    # create new file
    outfile = VectorData()
    outfile.fields = list(data.fields)
    
    # loop features
    if "LineString" in data.type or "Polygon" in data.type:
        for feat in data:
            if "Multi" in feat.geometry["type"]:
                multishape = feat.get_shapely()
                for geom in multishape.geoms:
                    shapelypoint = geom.centroid
                    geoj = shapelypoint.__geo_interface__
                    outfile.add_feature(feat.row, geoj)
            else:
                shapelypoint = feat.get_shapely().centroid
                geoj = shapelypoint.__geo_interface__
                outfile.add_feature(feat.row, geoj)
        return outfile
    
    else:
        return data.copy()

def _to_centroids(data):
    """create one centroid point for each multi geometry part"""
    
    # create new file
    outfile = VectorData()
    outfile.fields = list(data.fields)
    
    # loop features
    for feat in data:
        if feat.geometry["type"] != "Point":
            shapelypoint = feat.get_shapely().centroid
            geoj = shapelypoint.__geo_interface__
            outfile.add_feature(feat.row, geoj)
    return outfile

def _to_vertexes(data):
    """create points at every vertex, incl holes"""
    
    # create new file
    outfile = VectorData()
    outfile.fields = list(data.fields)
    
    # loop points
    if "LineString" in data.type:
        for feat in data:
            if "Multi" in feat.geometry["type"]:
                for linestring in feat.geometry["coordinates"]:
                    for point in linsetring:
                        geoj = {"type": "Point",
                                "coordinates": point}
                        outfile.add_feature(feat.row, geoj)
            else:
                for point in feat.geometry["coordinates"]:
                    geoj = {"type": "Point",
                            "coordinates": point}
                    outfile.add_feature(feat.row, geoj)
        return outfile
                        
    elif "Polygon" in data.type:
        for feat in data:
            if "Multi" in feat.geometry["type"]:
                for polygon in feat.geometry["coordinates"]:
                    for ext_or_hole in polygon:
                        for point in ext_or_hole:
                            geoj = {"type": "Point",
                                    "coordinates": point}
                            outfile.add_feature(feat.row, geoj)
            else:
                for ext_or_hole in feat.geometry["coordinates"]:
                    for point in ext_or_hole:
                        geoj = {"type": "Point",
                                "coordinates": point}
                        outfile.add_feature(feat.row, geoj)
        return outfile
    
    else:
        return data.copy()




# Converting between geometry types

def to_points(data, pointtype="vertex"):
    if pointtype == "vertex":
        return _to_vertexes(data)
    
    elif pointtype == "centroid":
        return _to_centroids(data)
    
    elif pointtype == "multicentroid":
        return _to_multicentroids(data)


