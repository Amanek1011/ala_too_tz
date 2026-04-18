import json
from django.http import Http404
from django.shortcuts import render

from .data import get_all_regions, get_region, get_highlights, get_landmark_icon


def home(request):
    regions = get_all_regions()
    cities = [
        {'id': 'bishkek', 'label': 'Bishkek', 'cx': 480, 'cy': 175},
        {'id': 'osh-city', 'label': 'Osh', 'cx': 292, 'cy': 400},
        {'id': 'karakol', 'label': 'Karakol', 'cx': 760, 'cy': 195},
        {'id': 'naryn-city', 'label': 'Naryn', 'cx': 540, 'cy': 295},
    ]
    return render(request, 'attractions/home.html', {
        'regions': regions,
        'regions_json': json.dumps(regions),
        'cities': cities,
    })


def region_detail(request, region_id):
    region = get_region(region_id)
    if region is None:
        raise Http404('Регион не найден')
    highlights = get_highlights(region_id)
    landmarks_with_icons = [
        {'name': landmark, 'icon': get_landmark_icon(landmark)}
        for landmark in region['landmarks']
    ]
    return render(request, 'attractions/region_detail.html', {
        'region': region,
        'highlights': highlights,
        'landmarks_with_icons': landmarks_with_icons,
    })
