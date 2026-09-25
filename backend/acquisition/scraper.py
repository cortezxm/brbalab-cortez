"""
Integrated League Data Acquisition Module

This module provides scrapers for different football competitions:
- EPL: English Premier League via fbref.com
- FIFA: International matches via 11v11.com with incremental updates and confederation support

Classes:
    LeagueConfig: Configuration class for league-specific parameters
    BaseScraper: Generic base scraper with common functionality  
    EPLScraper: EPL-specific implementation
    FIFAScraper: FIFA international matches implementation with venue tracking

Functions:
    get_epl_season_year: Calculate current EPL season year
    get_fifa_current_year: Get current year for FIFA scraping
"""

import ssl
import urllib.request
import re
import time
import threading
import requests
import os
import subprocess
import platform
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import List, Dict, Optional, Tuple, Any
from playwright.sync_api import sync_playwright
import logging

import bs4 as bs
import pandas as pd
import psutil
from selenium.webdriver import Chrome
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from fuzzywuzzy import fuzz
from geopy.geocoders import Nominatim

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_fifa_current_year():
    current_date = datetime.now()
    return current_date.year


class LeagueConfig:
    def __init__(self, name, url, season_start_month, season_end_month, scraper_type="", frequency_hours=24):
        self.name = name
        self.url = url
        self.season_start_month = season_start_month
        self.season_end_month = season_end_month
        self.scraper_type = scraper_type
        self.frequency_hours = frequency_hours
    
    def get_season_year(self):
        current_date = datetime.now()
        current_month = current_date.month
        current_year = current_date.year

        if current_month <= self.season_end_month:
            return current_year - 1
        else:
            return current_year


class FIFAConfig:
    GEOLOCATION_AVAILABLE = True
    GLOBAL_TIMEOUT = 45
    DETAIL_TIMEOUT = 35
    MAX_RETRIES = 3
    FUZZY_THRESHOLD = 70
    RATE_LIMIT_DELAY = 3
    BATCH_SIZE = 10

COUNTRY_TO_FIFA_CODE = {
    'Afghanistan': 'AFG', 'Albania': 'ALB', 'Algeria': 'ALG', 'American Samoa': 'ASA', 'Andorra': 'AND',
    'Angola': 'ANG', 'Anguilla': 'AIA', 'Antigua and Barbuda': 'ATG', 'Argentina': 'ARG', 'Armenia': 'ARM', 
    'Aruba': 'ARU', 'Australia': 'AUS', 'Austria': 'AUT', 'Azerbaijan': 'AZE', 'Bahamas': 'BAH', 
    'Bahrain': 'BHR', 'Bangladesh': 'BAN', 'Barbados': 'BRB', 'Belarus': 'BLR', 'Belgium': 'BEL', 
    'Belize': 'BLZ', 'Benin': 'BEN', 'Bermuda': 'BER', 'Bhutan': 'BHU', 'Bolivia': 'BOL', 
    'Bosnia-Herzegovina': 'BIH', 'Botswana': 'BOT', 'Brazil': 'BRA', 'British Virgin Islands': 'VGB', 
    'Brunei': 'BRU', 'Bulgaria': 'BUL', 'Burkina Faso': 'BFA', 'Burundi': 'BDI', 'Cambodia': 'CAM', 
    'Cameroon': 'CMR', 'Canada': 'CAN', 'Cabo Verde': 'CPV', 'Cayman Islands': 'CAY', 
    'Central African Republic': 'CTA', 'Chad': 'CHA', 'Chile': 'CHI', 'China PR': 'CHN', 'Taiwan': 'TPE', 
    'Colombia': 'COL', 'Comoros': 'COM', 'Congo': 'CGO', 'Congo DR': 'COD', 'Cook Islands': 'COK',
    'Costa Rica': 'CRC', "Cote d'Ivoire": 'CIV', 'Croatia': 'CRO', 'Cuba': 'CUB', 'Curacao': 'CUW',
    'Cyprus': 'CYP', 'Czechia': 'CZE', 'Denmark': 'DEN', 'Djibouti': 'DJI', 'Dominica': 'DMA',
    'Dominican Republic': 'DOM', 'Ecuador': 'ECU', 'Egypt': 'EGY', 'El Salvador': 'SLV', 'England': 'ENG', 
    'Equatorial Guinea': 'EQG', 'Eritrea': 'ERI', 'Estonia': 'EST', 'Eswatini': 'SWZ', 'Ethiopia': 'ETH', 
    'Faroe Islands': 'FRO', 'Fiji': 'FIJ', 'Finland': 'FIN', 'France': 'FRA', 'Gabon': 'GAB', 
    'Gambia': 'GAM', 'Georgia': 'GEO', 'Germany': 'GER', 'Ghana': 'GHA', 'Gibraltar': 'GIB', 
    'Greece': 'GRE', 'Grenada': 'GRN', 'Guam': 'GUM', 'Guatemala': 'GUA', 'Guinea': 'GUI',
    'Guinea-Bissau': 'GNB', 'Guyana': 'GUY', 'Haiti': 'HAI', 'Honduras': 'HON', 'Hong Kong': 'HKG',
    'Hungary': 'HUN', 'Iceland': 'ISL', 'India': 'IND', 'Indonesia': 'IDN', 'Iran': 'IRN', 'Iraq': 'IRQ', 
    'Israel': 'ISR', 'Italy': 'ITA', 'Jamaica': 'JAM', 'Japan': 'JPN', 'Jordan': 'JOR', 'Kazakhstan': 'KAZ', 
    'Kenya': 'KEN', 'North Korea': 'PRK', 'South Korea': 'KOR', 'Kosovo': 'KOS', 'Kuwait': 'KUW', 
    'Kyrgyzstan': 'KGZ', 'Laos': 'LAO', 'Latvia': 'LVA', 'Lebanon': 'LIB', 'Lesotho': 'LES', 
    'Liberia': 'LBR', 'Libya': 'LBY', 'Liechtenstein': 'LIE', 'Lithuania': 'LTU', 'Luxembourg': 'LUX', 
    'Macau': 'MAC', 'Madagascar': 'MAD', 'Malawi': 'MWI', 'Malaysia': 'MAS', 'Maldives': 'MDV',
    'Mali': 'MLI', 'Malta': 'MLT', 'Mauritania': 'MTN', 'Mauritius': 'MRI', 'Mexico': 'MEX',
    'Moldova': 'MDA', 'Mongolia': 'MNG', 'Montenegro': 'MNE', 'Montserrat': 'MSR', 'Morocco': 'MAR', 
    'Mozambique': 'MOZ', 'Myanmar': 'MYA', 'Namibia': 'NAM', 'Nepal': 'NEP', 'Netherlands': 'NED', 
    'New Caledonia': 'NCL', 'New Zealand': 'NZL', 'Nicaragua': 'NCA', 'Niger': 'NIG', 'Nigeria': 'NGA', 
    'North Macedonia': 'MKD', 'Northern Ireland': 'NIR', 'Norway': 'NOR', 'Oman': 'OMA', 'Pakistan': 'PAK', 
    'Palestine': 'PLE', 'Panama': 'PAN', 'Papua New Guinea': 'PNG', 'Paraguay': 'PAR', 'Peru': 'PER', 
    'Philippines': 'PHI', 'Poland': 'POL', 'Portugal': 'POR', 'Puerto Rico': 'PUR', 'Qatar': 'QAT', 
    'Republic of Ireland': 'IRL', 'Romania': 'ROU', 'Russia': 'RUS', 'Rwanda': 'RWA', 'Samoa': 'SAM',
    'San Marino': 'SMR', 'Sao Tomé e Príncipe': 'STP', 'Saudi Arabia': 'KSA', 'Scotland': 'SCO',
    'Senegal': 'SEN', 'Serbia': 'SRB', 'Seychelles': 'SEY', 'Sierra Leone': 'SLE', 'Singapore': 'SIN', 
    'Slovakia': 'SVK', 'Slovenia': 'SVN', 'Solomon Islands': 'SOL', 'Somalia': 'SOM', 'South Africa': 'RSA', 
    'South Sudan': 'SSD', 'Spain': 'ESP', 'Sri Lanka': 'SRI', 'St. Kitts and Nevis': 'SKN', 
    'St. Lucia': 'LCA', 'St. Vincent and the Grenadines': 'VIN', 'Sudan': 'SDN', 'Suriname': 'SUR', 
    'Sweden': 'SWE', 'Switzerland': 'SUI', 'Syria': 'SYR', 'Tahiti': 'TAH', 'Tajikistan': 'TJK', 
    'Tanzania': 'TAN', 'Thailand': 'THA', 'Timor-Leste': 'TLS', 'Togo': 'TOG', 'Tonga': 'TGA',
    'Trinidad and Tobago': 'TRI', 'Tunisia': 'TUN', 'Türkiye': 'TUR', 'Turkmenistan': 'TKM',
    'Turks and Caicos Islands': 'TCA', 'Uganda': 'UGA', 'Ukraine': 'UKR', 'United Arab Emirates': 'UAE',
    'Uruguay': 'URU', 'US Virgin Islands': 'VIR', 'USA': 'USA', 'Uzbekistan': 'UZB', 'Vanuatu': 'VAN', 
    'Venezuela': 'VEN', 'Vietnam': 'VIE', 'Wales': 'WAL', 'Yemen': 'YEM', 'Zambia': 'ZAM', 
    'Zimbabwe': 'ZIM', 'FYR Macedonia': 'FYR', "Côte d'Ivoire": 'CIV',
    'Democratic Republic of the Congo': 'COD', 'Congo-Brazzaville': 'CGO'
}

FIFA_COUNTRIES_11V11 = [
    'argentina', 'spain', 'france', 'england', 'brazil', 'portugal', 'netherlands', 'belgium', 'germany', 'croatia',
    'italy', 'morocco', 'mexico', 'colombia', 'usa', 'uruguay', 'japan', 'senegal', 'switzerland', 'iran',
    'denmark', 'austria', 'korea-republic', 'australia', 'ecuador', 'ukraine', 'turkey', 'canada', 'sweden', 'panama',
    'wales', 'serbia', 'norway', 'egypt', 'russia', 'algeria', 'poland', 'hungary', 'greece', 'costa-rica',
    'czech-republic', 'peru', 'paraguay', 'nigeria', 'ivory-coast', 'venezuela', 'scotland', 'romania', 'tunisia', 'slovenia',
    'cameroon', 'slovakia', 'qatar', 'mali', 'uzbekistan', 'south-africa', 'chile', 'iraq', 'saudi-arabia', 'republic-of-ireland',
    'congo-dr', 'north-macedonia', 'burkina-faso', 'jordan', 'united-arab-emirates', 'honduras', 'georgia', 'albania',
    'finland', 'jamaica', 'northern-ireland', 'bosnia-and-herzegovina', 'cape-verde-islands', 'iceland', 'israel', 'ghana', 'montenegro',
    'bolivia', 'oman', 'gabon', 'guinea', 'new-zealand', 'zambia', 'bulgaria', 'angola', 'curacao', 'el-salvador',
    'uganda', 'bahrain', 'haiti', 'syria', 'luxembourg', 'equatorial-guinea', 'china-pr', 'kosovo', 'benin', 'belarus',
    'palestine', 'mozambique', 'guatemala', 'trinidad-and-tobago', 'thailand', 'tanzania', 'kyrgyzstan', 'armenia', 'tajikistan',
    'comoros', 'namibia', 'kenya', 'sudan', 'mauritania', 'lebanon', 'vietnam', 'kazakhstan', 'madagascar', 'zimbabwe',
    'libya', 'indonesia', 'korea-dpr', 'togo', 'niger', 'azerbaijan', 'gambia', 'sierra-leone', 'malaysia', 'estonia',
    'rwanda', 'cyprus', 'malawi', 'nicaragua', 'guinea-bissau', 'congo', 'india', 'central-african-republic', 'botswana',
    'suriname', 'latvia', 'kuwait', 'burundi', 'turkmenistan', 'faroe-islands', 'dominican-republic', 'lithuania', 'liberia',
    'philippines', 'ethiopia', 'hong-kong', 'lesotho', 'solomon-islands', 'fiji', 'st-kitts-and-nevis', 'new-caledonia', 'guyana',
    'moldova', 'swaziland', 'yemen', 'puerto-rico', 'tahiti', 'singapore', 'myanmar', 'afghanistan', 'bermuda', 'antigua-and-barbuda',
    'vanuatu', 'st-lucia', 'cuba', 'grenada', 'malta', 'south-sudan', 'papua-new-guinea', 'maldives', 'chinese-taipei',
    'st-vincent-and-the-grenadines', 'andorra', 'chad', 'nepal', 'mauritius', 'barbados', 'montserrat', 'cambodia', 'belize',
    'dominica', 'brunei-darussalam', 'bangladesh', 'laos', 'bhutan', 'american-samoa', 'mongolia', 'cook-islands', 'samoa', 'djibouti',
    'macau', 'sao-tome-e-principe', 'aruba', 'timor-leste', 'sri-lanka', 'cayman-islands', 'tonga', 'gibraltar', 'somalia', 'pakistan',
    'guam', 'seychelles', 'liechtenstein', 'bahamas', 'turks-and-caicos-islands', 'us-virgin-islands', 'british-virgin-islands',
    'anguilla', 'san-marino'
]

URL_NAME_TO_FIFA_CODE = {
    'argentina': 'ARG', 'spain': 'ESP', 'france': 'FRA', 'england': 'ENG', 'brazil': 'BRA',
    'portugal': 'POR', 'netherlands': 'NED', 'belgium': 'BEL', 'germany': 'GER', 'croatia': 'CRO',
    'italy': 'ITA', 'morocco': 'MAR', 'mexico': 'MEX', 'colombia': 'COL', 'usa': 'USA',
    'uruguay': 'URU', 'japan': 'JPN', 'senegal': 'SEN', 'switzerland': 'SUI', 'iran': 'IRN',
    'denmark': 'DEN', 'austria': 'AUT', 'korea-republic': 'KOR', 'australia': 'AUS', 'ecuador': 'ECU',
    'ukraine': 'UKR', 'turkey': 'TUR', 'canada': 'CAN', 'sweden': 'SWE', 'panama': 'PAN',
    'wales': 'WAL', 'serbia': 'SRB', 'norway': 'NOR', 'egypt': 'EGY', 'russia': 'RUS',
    'algeria': 'ALG', 'poland': 'POL', 'hungary': 'HUN', 'greece': 'GRE', 'costa-rica': 'CRC',
    'czech-republic': 'CZE', 'peru': 'PER', 'paraguay': 'PAR', 'nigeria': 'NGA', 'ivory-coast': 'CIV',
    'venezuela': 'VEN', 'scotland': 'SCO', 'romania': 'ROU', 'tunisia': 'TUN', 'slovenia': 'SVN',
    'cameroon': 'CMR', 'slovakia': 'SVK', 'qatar': 'QAT', 'mali': 'MLI', 'uzbekistan': 'UZB',
    'south-africa': 'RSA', 'chile': 'CHI', 'iraq': 'IRQ', 'saudi-arabia': 'KSA', 'republic-of-ireland': 'IRL',
    'congo-dr': 'COD', 'north-macedonia': 'MKD', 'burkina-faso': 'BFA', 'jordan': 'JOR',
    'united-arab-emirates': 'UAE', 'honduras': 'HON', 'georgia': 'GEO', 'albania': 'ALB',
    'finland': 'FIN', 'jamaica': 'JAM', 'northern-ireland': 'NIR', 'bosnia-and-herzegovina': 'BIH',
    'cape-verde-islands': 'CPV', 'iceland': 'ISL', 'israel': 'ISR', 'ghana': 'GHA', 'montenegro': 'MNE',
    'bolivia': 'BOL', 'oman': 'OMA', 'gabon': 'GAB', 'guinea': 'GUI', 'new-zealand': 'NZL',
    'zambia': 'ZAM', 'bulgaria': 'BUL', 'angola': 'ANG', 'curacao': 'CUW', 'el-salvador': 'SLV',
    'uganda': 'UGA', 'bahrain': 'BHR', 'haiti': 'HAI', 'syria': 'SYR', 'luxembourg': 'LUX',
    'equatorial-guinea': 'EQG', 'china-pr': 'CHN', 'kosovo': 'KOS', 'benin': 'BEN', 'belarus': 'BLR',
    'palestine': 'PLE', 'mozambique': 'MOZ', 'guatemala': 'GUA', 'trinidad-and-tobago': 'TRI',
    'thailand': 'THA', 'tanzania': 'TAN', 'kyrgyzstan': 'KGZ', 'armenia': 'ARM', 'tajikistan': 'TJK',
    'comoros': 'COM', 'namibia': 'NAM', 'kenya': 'KEN', 'sudan': 'SDN', 'mauritania': 'MTN',
    'lebanon': 'LIB', 'vietnam': 'VIE', 'kazakhstan': 'KAZ', 'madagascar': 'MAD', 'zimbabwe': 'ZIM',
    'libya': 'LBY', 'indonesia': 'IDN', 'korea-dpr': 'PRK', 'togo': 'TOG', 'niger': 'NIG',
    'azerbaijan': 'AZE', 'gambia': 'GAM', 'sierra-leone': 'SLE', 'malaysia': 'MAS', 'estonia': 'EST',
    'rwanda': 'RWA', 'cyprus': 'CYP', 'malawi': 'MWI', 'nicaragua': 'NCA', 'guinea-bissau': 'GNB',
    'congo': 'CGO', 'india': 'IND', 'central-african-republic': 'CTA', 'botswana': 'BOT',
    'suriname': 'SUR', 'latvia': 'LVA', 'kuwait': 'KUW', 'burundi': 'BDI', 'turkmenistan': 'TKM',
    'faroe-islands': 'FRO', 'dominican-republic': 'DOM', 'lithuania': 'LTU', 'liberia': 'LBR',
    'philippines': 'PHI', 'ethiopia': 'ETH', 'hong-kong': 'HKG', 'lesotho': 'LES', 'solomon-islands': 'SOL',
    'fiji': 'FIJ', 'st-kitts-and-nevis': 'SKN', 'new-caledonia': 'NCL', 'guyana': 'GUY',
    'moldova': 'MDA', 'swaziland': 'SWZ', 'yemen': 'YEM', 'puerto-rico': 'PUR', 'tahiti': 'TAH',
    'singapore': 'SIN', 'myanmar': 'MYA', 'afghanistan': 'AFG', 'bermuda': 'BER', 'antigua-and-barbuda': 'ATG',
    'vanuatu': 'VAN', 'st-lucia': 'LCA', 'cuba': 'CUB', 'grenada': 'GRN', 'malta': 'MLT',
    'south-sudan': 'SSD', 'papua-new-guinea': 'PNG', 'maldives': 'MDV', 'chinese-taipei': 'TPE',
    'st-vincent-and-the-grenadines': 'VIN', 'andorra': 'AND', 'chad': 'CHA', 'nepal': 'NEP',
    'mauritius': 'MRI', 'barbados': 'BRB', 'montserrat': 'MSR', 'cambodia': 'CAM', 'belize': 'BLZ',
    'dominica': 'DMA', 'brunei-darussalam': 'BRU', 'bangladesh': 'BAN', 'laos': 'LAO', 'bhutan': 'BHU',
    'american-samoa': 'ASA', 'mongolia': 'MNG', 'cook-islands': 'COK', 'samoa': 'SAM', 'djibouti': 'DJI',
    'macau': 'MAC', 'sao-tome-e-principe': 'STP', 'aruba': 'ARU', 'timor-leste': 'TLS', 'sri-lanka': 'SRI',
    'cayman-islands': 'CAY', 'tonga': 'TGA', 'gibraltar': 'GIB', 'somalia': 'SOM', 'pakistan': 'PAK',
    'guam': 'GUM', 'seychelles': 'SEY', 'liechtenstein': 'LIE', 'bahamas': 'BAH',
    'turks-and-caicos-islands': 'TCA', 'us-virgin-islands': 'VIR', 'british-virgin-islands': 'VGB',
    'anguilla': 'AIA', 'san-marino': 'SMR'
}

FIFA_CODE_TO_COUNTRY = {v: k.replace('-', ' ').title() for k, v in URL_NAME_TO_FIFA_CODE.items()}
FIFA_CODE_TO_COUNTRY.update({
    'USA': 'United States', 'KOR': 'South Korea', 'IRL': 'Ireland', 'COD': 'Democratic Republic of the Congo',
    'CIV': 'Ivory Coast', 'CRC': 'Costa Rica', 'CZE': 'Czech Republic', 'MKD': 'North Macedonia',
    'BIH': 'Bosnia and Herzegovina', 'UAE': 'United Arab Emirates', 'KSA': 'Saudi Arabia',
    'RSA': 'South Africa', 'BFA': 'Burkina Faso', 'NIR': 'Northern Ireland', 'CPV': 'Cape Verde',
    'EQG': 'Equatorial Guinea', 'CHN': 'China PR', 'TRI': 'Trinidad and Tobago', 'TAN': 'Tanzania',
    'PRK': 'North Korea', 'SLE': 'Sierra Leone', 'CTA': 'Central African Republic', 'DOM': 'Dominican Republic',
    'SOL': 'Solomon Islands', 'SKN': 'St. Kitts and Nevis', 'NCL': 'New Caledonia', 'SWZ': 'Eswatini',
    'PUR': 'Puerto Rico', 'ATG': 'Antigua and Barbuda', 'LCA': 'St. Lucia', 'SSD': 'South Sudan',
    'PNG': 'Papua New Guinea', 'TPE': 'Chinese Taipei', 'VIN': 'St. Vincent and the Grenadines',
    'BRU': 'Brunei Darussalam', 'ASA': 'American Samoa', 'COK': 'Cook Islands', 'STP': 'Sao Tome e Principe',
    'TLS': 'Timor-Leste', 'SRI': 'Sri Lanka', 'CAY': 'Cayman Islands', 'TCA': 'Turks and Caicos Islands',
    'VIR': 'US Virgin Islands', 'VGB': 'British Virgin Islands', 'SMR': 'San Marino'
})

CONTINENTAL_GROUPS = {
    'UEFA': [
        'ALB', 'AND', 'ARM', 'AUT', 'AZE', 'BEL', 'BIH', 'BLR', 'BUL', 'CRO', 'CYP', 'CZE', 'DEN', 
        'ENG', 'ESP', 'EST', 'FRO', 'FIN', 'FRA', 'GEO', 'GER', 'GIB', 'GRE', 'HUN', 'ISL', 'IRL', 
        'ITA', 'KOS', 'KAZ', 'LVA', 'LIE', 'LTU', 'LUX', 'MLT', 'MDA', 'MNE', 'NED', 'NIR', 'NOR', 
        'POL', 'POR', 'ROU', 'RUS', 'SCO', 'SRB', 'SVK', 'SVN', 'SWE', 'SUI', 'TUR', 'UKR', 'WAL'
    ],
    'CAF': [
        'ALG', 'ANG', 'BEN', 'BOT', 'BFA', 'BDI', 'CMR', 'CPV', 'CTA', 'CHA', 'COM', 'CGO', 'COD', 
        'CIV', 'DJI', 'EGY', 'EQG', 'ERI', 'SWZ', 'ETH', 'GAB', 'GAM', 'GHA', 'GUI', 'GNB', 'KEN', 
        'LES', 'LBR', 'LBY', 'MAD', 'MWI', 'MLI', 'MTN', 'MRI', 'MAR', 'MOZ', 'NAM', 'NIG', 'NGA', 
        'RWA', 'STP', 'SEN', 'SEY', 'SLE', 'SOM', 'RSA', 'SSD', 'SDN', 'TAN', 'TOG', 'TUN', 'UGA', 
        'ZAM', 'ZIM'
    ],
    'AFC': [
        'AFG', 'BHR', 'BAN', 'BHU', 'BRU', 'CAM', 'CHN', 'TPE', 'PRK', 'KOR', 'HKG', 'IND', 'IDN', 
        'IRN', 'IRQ', 'ISR', 'JPN', 'JOR', 'KUW', 'KGZ', 'LAO', 'LIB', 'MAC', 'MAS', 'MDV', 'MNG', 
        'MYA', 'NEP', 'OMA', 'PAK', 'PLE', 'PHI', 'QAT', 'KSA', 'SIN', 'SRI', 'SYR', 'TJK', 'THA', 
        'TLS', 'TKM', 'UAE', 'UZB', 'VIE', 'YEM'
    ],
    'CONCACAF': [
        'AIA', 'ATG', 'BRB', 'BLZ', 'BER', 'CAN', 'CAY', 'CRC', 'CUB', 'CUW', 'DMA', 'DOM', 
        'SLV', 'GUA', 'GUY', 'HAI', 'HON', 'JAM', 'MEX', 'MSR', 'NCA', 'PAN', 'PUR', 'SKN', 
        'LCA', 'VIN', 'SUR', 'TRI', 'TCA', 'USA', 'VIR'
    ],
    'CONMEBOL': [
        'ARG', 'BOL', 'BRA', 'CHI', 'COL', 'ECU', 'PAR', 'PER', 'URU', 'VEN'
    ],
    'OFC': [
        'ASA', 'AUS', 'COK', 'FIJ', 'NCL', 'NZL', 'PNG', 'SAM', 'SOL', 'TAH', 'TGA', 'VAN'
    ]
}

EPL_CONFIG = LeagueConfig(
    name="EPL",
    url="https://fbref.com/en/comps/9/schedule/Premier-League-Scores-and-Fixtures",
    season_start_month=8,
    season_end_month=7,
    scraper_type="",
    frequency_hours=24
)

FIFA_CONFIG = LeagueConfig(
    name="FIFA", 
    url="https://www.11v11.com/",
    season_start_month=1,
    season_end_month=12,
    scraper_type="",
    frequency_hours=4320
)

LEAGUE_CONFIGS = {
    "EPL": EPL_CONFIG,
    "FIFA": FIFA_CONFIG
}


class PerformanceTimer:
    def __init__(self, operation_name: str):
        self.operation_name = operation_name
        self.start_time = None
        self.end_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        logger.info(f"Starting {self.operation_name}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        duration = self.end_time - self.start_time
        logger.info(f"Completed {self.operation_name} in {duration:.2f} seconds")


class ChromeProcessManager:
    @staticmethod
    def kill_all_chrome_processes() -> int:
        system = platform.system().lower()
        killed_count = 0
        
        try:
            if system == "windows":
                processes_to_kill = ["chrome.exe", "chromedriver.exe", "chromium.exe"]
                for process_name in processes_to_kill:
                    try:
                        result = subprocess.run([
                            "taskkill", "/F", "/IM", process_name, "/T"
                        ], capture_output=True, text=True, timeout=10)
                        if result.returncode == 0:
                            killed_count += 1
                    except (subprocess.TimeoutExpired, Exception):
                        continue
            else:
                processes_to_kill = ["chrome", "chromium", "chromedriver", "google-chrome"]
                for process_name in processes_to_kill:
                    try:
                        result = subprocess.run([
                            "pkill", "-f", process_name
                        ], capture_output=True, timeout=10)
                        if result.returncode == 0:
                            killed_count += 1
                    except (subprocess.TimeoutExpired, Exception):
                        continue
            
            try:
                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                    try:
                        proc_info = proc.info
                        name = proc_info['name'].lower() if proc_info['name'] else ''
                        cmdline = ' '.join(proc_info['cmdline']).lower() if proc_info['cmdline'] else ''
                        
                        if any(chrome_name in name or chrome_name in cmdline 
                               for chrome_name in ['chrome', 'chromium', 'chromedriver']):
                            proc.kill()
                            killed_count += 1
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        continue
            except Exception:
                pass
                
        except Exception as e:
            logger.warning(f"Error during Chrome process cleanup: {e}")
        
        if killed_count > 0:
            time.sleep(2)
            
        return killed_count
    
    @staticmethod
    def get_chrome_options() -> Options:
        chrome_options = Options()
        
        options_list = [
            '--log-level=3', '--disable-gpu', '--no-sandbox', '--disable-dev-shm-usage',
            '--disable-extensions', '--disable-web-security',
            '--disable-features=VizDisplayCompositor,TranslateUI,BlinkGenPropertyTrees',
            '--disable-backgrounding-occluded-windows', '--disable-renderer-backgrounding',
            '--disable-background-timer-throttling', '--disable-background-networking',
            '--disable-ipc-flooding-protection', '--disable-hang-monitor',
            '--disable-prompt-on-repost', '--disable-domain-reliability',
            '--disable-component-update', '--disable-default-apps', '--disable-sync',
            '--disable-translate', '--disable-notifications', '--disable-plugins',
            '--timeout=30000', '--page-load-timeout=30000', '--script-timeout=20000',
            '--memory-pressure-off', '--max_old_space_size=4096',
            '--aggressive-cache-discard', '--network-service-in-process',
            '--disable-blink-features=AutomationControlled'
        ]
        
        for option in options_list:
            chrome_options.add_argument(option)
        
        chrome_options.page_load_strategy = 'eager'
        chrome_options.add_experimental_option('excludeSwitches', [
            'enable-logging', 'enable-automation', 'enable-blink-features'
        ])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        return chrome_options


class ProcessMonitor:
    def __init__(self):
        self.tracked_pids = set()
        self.is_monitoring = False
        self.monitor_thread = None
    
    def start_monitoring(self):
        if not self.is_monitoring:
            self.is_monitoring = True
            self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.monitor_thread.start()
    
    def stop_monitoring(self):
        self.is_monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        self._kill_tracked_processes()
    
    def add_process(self, pid: int):
        if pid:
            self.tracked_pids.add(pid)
    
    def _monitor_loop(self):
        while self.is_monitoring:
            try:
                time.sleep(10)
                self._check_hanging_processes()
            except Exception:
                pass
    
    def _check_hanging_processes(self):
        for pid in list(self.tracked_pids):
            try:
                if psutil.pid_exists(pid):
                    proc = psutil.Process(pid)
                    if time.time() - proc.create_time() > 120:
                        proc.kill()
                        self.tracked_pids.discard(pid)
                else:
                    self.tracked_pids.discard(pid)
            except Exception:
                self.tracked_pids.discard(pid)
    
    def _kill_tracked_processes(self):
        for pid in list(self.tracked_pids):
            try:
                if psutil.pid_exists(pid):
                    psutil.Process(pid).kill()
            except Exception:
                pass
        self.tracked_pids.clear()


process_monitor = ProcessMonitor()


@contextmanager
def driver_get(driver, url: str, timeout: int = 40):
    result = {'success': False, 'error': None, 'thread_alive': False}
    
    def target():
        try:
            driver.get(url)
            result['success'] = True
        except Exception as e:
            result['error'] = e
        finally:
            result['thread_alive'] = False
    
    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    result['thread_alive'] = True
    
    thread.join(timeout)
    
    if thread.is_alive():
        result['thread_alive'] = True
        logger.warning(f"Navigation timeout for {url}")
        
        try:
            driver.quit()
        except:
            pass
        
        ChromeProcessManager.kill_all_chrome_processes()
        thread.join(5)
        
        if thread.is_alive():
            ChromeProcessManager.kill_all_chrome_processes()
        
        raise TimeoutException(f"Navigation timed out after {timeout} seconds")
    
    if result['error']:
        raise result['error']
    
    if not result['success']:
        raise Exception("Navigation failed for unknown reason")
    
    yield


class ChromeDriver:
    def __init__(self, timeout: int = None):
        self.timeout = timeout or FIFAConfig.GLOBAL_TIMEOUT
        self.driver = None
        self.process_id = None
        self.options = ChromeProcessManager.get_chrome_options()
    
    def __enter__(self):
        process_monitor.start_monitoring()
        self._initialize_driver()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self._cleanup()
        process_monitor.stop_monitoring()
    
    def _initialize_driver(self):
        ChromeProcessManager.kill_all_chrome_processes()
        time.sleep(1)
        
        try:
            self.driver = Chrome(options=self.options)
            self.driver.set_page_load_timeout(self.timeout)
            self.driver.implicitly_wait(5)
            
            try:
                self.process_id = self.driver.service.process.pid
                process_monitor.add_process(self.process_id)
            except:
                pass
        except Exception as e:
            logger.error(f"Failed to initialize Chrome driver: {e}")
            ChromeProcessManager.kill_all_chrome_processes()
            raise
    
    def safe_get(self, url: str, max_retries: int = 1) -> bool:
        for attempt in range(max_retries):
            try:
                with driver_get(self.driver, url, self.timeout):
                    return True
            except Exception as e:
                logger.warning(f"Navigation attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    self._cleanup()
                    time.sleep(3)
                    self._initialize_driver()
                else:
                    logger.error("All navigation attempts failed")
                    raise
        return False
    
    def _cleanup(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                logger.warning(f"Driver quit failed: {e}")
            finally:
                self.driver = None
        
        ChromeProcessManager.kill_all_chrome_processes()
        self.process_id = None


class GeolocationService:
    @staticmethod
    def get_country_from_venue(venue_name: str, timeout: int = 15) -> str:
        if not FIFAConfig.GEOLOCATION_AVAILABLE or not venue_name:
            return "Location not found"
        
        try:
            geolocator = Nominatim(user_agent="11v11_scraper", timeout=timeout)
            result = geolocator.geocode(venue_name, language='en')
            
            if result is None:
                logger.debug(f"Geolocation failed for venue: {venue_name}")
                return "Location not found"
            
            address = result.address
            country = address.split(',')[-1].strip()
            return country
            
        except Exception as e:
            logger.debug(f"Geolocation error for {venue_name}: {e}")
            return "Location not found"


class VenueTracker:
    def __init__(self, data_dir="FIFA_data_files"):
        self.data_dir = data_dir
        self.venues_found_file = os.path.join(data_dir, "venues_found.txt")
        self.venue_mapping_file = os.path.join(data_dir, "venue_country_mapping.txt")
        self.failed_venues_file = os.path.join(data_dir, "failed_venues.txt")
        
        self.venues_found = set()
        self.failed_venues = set()
        self.venue_mapping = {}
        
        self._ensure_directory()
        self._load_venue_mapping()
    
    def _ensure_directory(self):
        os.makedirs(self.data_dir, exist_ok=True)
    
    def _load_venue_mapping(self):
        try:
            if os.path.exists(self.venue_mapping_file):
                with open(self.venue_mapping_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if '->' in line and not line.startswith('#'):
                            venue, country = line.split('->', 1)
                            self.venue_mapping[venue.strip()] = country.strip()
                
                logger.info(f"Loaded {len(self.venue_mapping)} manual venue mappings")
            else:
                with open(self.venue_mapping_file, 'w', encoding='utf-8') as f:
                    f.write("# Manual venue to country mapping\n")
                    f.write("# Format: venue_name -> country_name\n")
                    f.write("# Example: Wembley Stadium -> England\n")
                    f.write("# Example: Camp Nou -> Spain\n\n")
                
                logger.info(f"Created venue mapping template at {self.venue_mapping_file}")
                
        except Exception as e:
            logger.error(f"Error loading venue manual mapping: {e}")
    
    def add_venue_found(self, venue_name: str):
        if venue_name and venue_name.strip():
            self.venues_found.add(venue_name.strip())
    
    def add_failed_venue(self, venue_name: str):
        if venue_name and venue_name.strip():
            self.failed_venues.add(venue_name.strip())
    
    def get_venue_country(self, venue_name: str) -> Optional[str]:
        if not venue_name:
            return None
        
        if venue_name in self.venue_mapping:
            return self.venue_mapping[venue_name]
        
        country = GeolocationService.get_country_from_venue(venue_name)
        
        if "not found" in country.lower():
            self.add_failed_venue(venue_name)
            return None
        
        return country
    
    def save_all_venue_files(self):
        try:
            if self.venues_found:
                existing_venues = set()
                if os.path.exists(self.venues_found_file):
                    with open(self.venues_found_file, 'r', encoding='utf-8') as f:
                        existing_venues = set(line.strip() for line in f if line.strip())
                
                all_venues = existing_venues.union(self.venues_found)
                
                with open(self.venues_found_file, 'w', encoding='utf-8') as f:
                    for venue in sorted(all_venues):
                        f.write(f"{venue}\n")
                
                new_venues = len(self.venues_found - existing_venues)
                logger.info(f"Saved {len(all_venues)} total venues ({new_venues} new) to {self.venues_found_file}")
            
            if self.failed_venues:
                existing_failed = set()
                if os.path.exists(self.failed_venues_file):
                    with open(self.failed_venues_file, 'r', encoding='utf-8') as f:
                        existing_failed = set(line.strip() for line in f if line.strip())
                
                all_failed = existing_failed.union(self.failed_venues)
                
                with open(self.failed_venues_file, 'w', encoding='utf-8') as f:
                    f.write("# Venues that failed geolocation\n")
                    f.write("# Add these to venue_country_mapping.txt with format: venue_name -> country_name\n\n")
                    for venue in sorted(all_failed):
                        f.write(f"{venue}\n")
                
                new_failed = len(self.failed_venues - existing_failed)
                logger.info(f"Saved {len(all_failed)} failed venues ({new_failed} new) to {self.failed_venues_file}")
                
        except Exception as e:
            logger.error(f"Error saving venue files: {e}")


class BaseScraper(ABC):
    def __init__(self, config):
        self.config = config
        self.season_year = config.get_season_year()
    
    def _create_ssl_context(self):
        return ssl.create_default_context()
    
    @abstractmethod
    def scrape_data(self):
        pass


class EPLScraper(BaseScraper):
    def __init__(self):
        super().__init__(EPL_CONFIG)
    
    def _fetch_page_content(self):

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False)  # pon headless=True si no quieres ver la ventana
                page = browser.new_page()
                page.goto(self.config.url, wait_until="networkidle")  # espera a que termine la carga
                sourceEPL = page.content()
                browser.close()
            # response = urllib.request.urlopen(self.config.url, context=context)
            # response = requests.get(self.config.url, headers=headers)
            # response.raise_for_status()
            # return response.read()
            return sourceEPL
        except Exception as e:
            raise Exception(f"Failed to fetch {self.config.name} data: {str(e)}")
    
    def _parse_html_content(self, content):
        soup = bs.BeautifulSoup(content, "lxml")
        schedule_divs = soup.find("table", {"id": re.compile("^sched_")})
        
        if schedule_divs is None:
            raise Exception("Could not find fixtures table in EPL page")
            
        # fixtures_table = schedule_divs[0]
        table_rows = schedule_divs.find_all("tr")
        
        return table_rows
    
    def _extract_row_data(self, table_rows):
        games_data = []
        gameweek_mapping = {}
        
        row_list = []
        for tr in table_rows:
            th = tr.find_all("th")
            date = [i.text for i in th]
            td = tr.find_all("td")
            row = [i.text for i in td]
            nwrow = date + row
            row_list.append(nwrow)
        
        for row in row_list:
            if len(row) < 13:
                continue
            
            if len(row) > 12:
                del row[9:13]
            
            if len(row) > 2 and row[0] and row[2]:
                gameweek_mapping[row[2]] = row[0]
            
            if len(row) > 2:
                del row[:2]
            
            if len(row) < 7 or row[0] == 'Date' or row[0] == "":
                continue
            
            date = row[0]
            home_team = row[2]
            away_team = row[6]
            
            try:
                if len(row) > 4 and row[4]:
                    home_score = int(row[4][0:1])
                    away_score = int(row[4][-1])
                else:
                    home_score = -1
                    away_score = -1
            except (IndexError, ValueError):
                home_score = -1
                away_score = -1
            
            if date and home_team and away_team:
                game_record = {
                    'id': f"{date},{home_team},{away_team}",
                    'date': date,
                    'gameweek': gameweek_mapping.get(date, ''),
                    'home_team': home_team,
                    'away_team': away_team,
                    'home_score': home_score,
                    'away_score': away_score
                }
                games_data.append(game_record)
        
        return games_data, gameweek_mapping
    
    def scrape_data(self):
        try:
            with PerformanceTimer(f"EPL scraping"):
                content = self._fetch_page_content()
                table_rows = self._parse_html_content(content)
                
                games_data, gameweek_mapping = self._extract_row_data(table_rows)
                
                games_df = pd.DataFrame(games_data)
                
                if not games_df.empty:
                    games_df['date'] = pd.to_datetime(games_df['date'])
                    games_df = games_df.sort_values('date').reset_index(drop=True)
                    games_df['date'] = games_df['date'].dt.strftime('%Y-%m-%d')
                
                metadata = {
                    'scraper_type': 'EPL',
                    'season_year': self.season_year,
                    'total_games': len(games_df),
                    'total_teams': len(set(games_df['home_team'].unique()) | set(games_df['away_team'].unique())) if not games_df.empty else 0,
                    'gameweek_mapping': gameweek_mapping,
                    'success': True
                }
                
                return games_df, metadata
                
        except Exception as e:
            empty_df = pd.DataFrame(columns=['id', 'date', 'gameweek', 'home_team', 'away_team', 'home_score', 'away_score'])
            error_metadata = {
                'scraper_type': 'EPL',
                'season_year': self.season_year,
                'total_games': 0,
                'total_teams': 0,
                'gameweek_mapping': {},
                'success': False,
                'error': str(e)
            }
            logger.error(f"EPL scraping failed: {e}")
            return empty_df, error_metadata


class FIFAScraper(BaseScraper):
    def __init__(self):
        super().__init__(FIFA_CONFIG)
        
        self.season_year = get_fifa_current_year()
        
        self.stats = {
            'total_matches': 0,
            'total_countries': len(FIFA_COUNTRIES_11V11),
            'successful_countries': [],
            'failed_countries': [],
            'venues_found': 0,
            'neutral_pitch_matches': 0
        }
        
        self.venue_tracker = VenueTracker()
    
    def get_confederation_countries(self, confederation: str) -> List[str]:
        if confederation not in CONTINENTAL_GROUPS:
            raise ValueError(f"Invalid confederation. Choose from: {list(CONTINENTAL_GROUPS.keys())}")
        
        confederation_codes = CONTINENTAL_GROUPS[confederation]
        confederation_countries = []
        
        for country_url in FIFA_COUNTRIES_11V11:
            fifa_code = URL_NAME_TO_FIFA_CODE.get(country_url)
            if fifa_code in confederation_codes:
                confederation_countries.append(country_url)
        
        logger.info(f"{confederation} confederation: {len(confederation_countries)} countries")
        return confederation_countries
    
    def scrape_confederation(self, confederation: str) -> Tuple[pd.DataFrame, Dict]:
        try:
            logger.info(f"Starting {confederation} confederation scraping")
            
            confederation_countries = self.get_confederation_countries(confederation)
            
            global FIFA_COUNTRIES_11V11
            original_countries = FIFA_COUNTRIES_11V11.copy()
            FIFA_COUNTRIES_11V11 = confederation_countries
            
            self.stats['total_countries'] = len(confederation_countries)
            
            matches_df, metadata = self.scrape_data()
            
            FIFA_COUNTRIES_11V11 = original_countries
            
            metadata['confederation'] = confederation
            metadata['confederation_countries'] = len(confederation_countries)
            
            logger.info(f"{confederation} scraping completed: {len(matches_df)} matches")
            
            return matches_df, metadata
            
        except Exception as e:
            FIFA_COUNTRIES_11V11 = original_countries
            logger.error(f"{confederation} confederation scraping failed: {e}")
            
            empty_df = pd.DataFrame(columns=['index', 'date', 'home_team', 'away_team', 'result', 'pso', 'competition', 'neutral_pitch'])
            error_metadata = {
                'scraper_type': 'FIFA',
                'confederation': confederation,
                'season_year': self.season_year,
                'total_matches': 0,
                'confederation_countries': 0,
                'success': False,
                'error': str(e)
            }
            return empty_df, error_metadata
    
    def load_historical_data(self, csv_path="FIFA_data_files/AllGames_raw.csv"):
        try:
            alternative_paths = [
                csv_path,
                "../../FIFA_data_files/AllGames_raw.csv",
                "../FIFA_data_files/AllGames.csv", 
                "FIFA_data_files/AllGames.csv"
            ]
            
            working_path = None
            for path in alternative_paths:
                if os.path.exists(path):
                    working_path = path
                    break
            
            if not working_path:
                logger.error(f"No historical data found at any of these paths: {alternative_paths}")
                return None, None
            
            historical_df = pd.read_csv(working_path, index_col=0)
            
            if historical_df.empty:
                logger.warning("Historical CSV exists but is empty")
                return None, None
            
            if 'home' in historical_df.columns and 'home_team' not in historical_df.columns:
                historical_df = historical_df.rename(columns={'home': 'home_team', 'away': 'away_team'})
            
            if 'neutral_pitch' in historical_df.columns:
                if historical_df['neutral_pitch'].dtype == 'object':
                    historical_df['neutral_pitch'] = historical_df['neutral_pitch'].map({
                        'yes': True, 
                        'no': False,
                        True: True,
                        False: False
                    }).fillna(False)
            
            historical_df['date'] = pd.to_datetime(historical_df['date'])
            last_date = historical_df['date'].max()
            last_date_str = last_date.strftime('%Y-%m-%d')
            
            historical_df['date'] = historical_df['date'].dt.strftime('%Y-%m-%d')
            
            logger.info(f"Loaded {len(historical_df)} historical matches. Last date: {last_date_str}")
            
            return historical_df, last_date_str
            
        except Exception as e:
            logger.error(f"Error loading historical data: {e}")
            return None, None
    
    def save_complete_data(self, df, csv_path="FIFA_data_files/AllGames.csv"):
        try:
            os.makedirs(os.path.dirname(csv_path), exist_ok=True)
            
            if not df.empty:
                df['date'] = pd.to_datetime(df['date'])
                df = df.sort_values('date').reset_index(drop=True)
                df['date'] = df['date'].dt.strftime('%Y-%m-%d')
            
            df.to_csv(csv_path, index=True)
            logger.info(f"Saved {len(df)} matches to {csv_path}")
            
        except Exception as e:
            logger.error(f"Error saving complete data: {e}")
            raise
    
    def filter_new_matches(self, all_matches, since_date):
        if not since_date:
            logger.info("No filter date - saving all matches")
            return all_matches
        
        try:
            cutoff_date = datetime(2023, 1, 1)
            new_matches = []
            
            for match in all_matches:
                try:
                    match_date_dt = datetime.strptime(match['date'], '%Y-%m-%d')
                    if match_date_dt >= cutoff_date:
                        new_matches.append(match)
                except ValueError:
                    new_matches.append(match)
                    continue
            
            logger.info(f"Comprehensive filter: Kept {len(new_matches)}/{len(all_matches)} matches (cutoff: 2023-01-01)")
            return new_matches
            
        except Exception as e:
            logger.error(f"Filter error - saving all matches: {e}")
            return all_matches
    
    def merge_with_historical(self, new_df, historical_df):
        try:
            if historical_df is None or historical_df.empty:
                logger.info("No historical data to merge with")
                return new_df
            
            if new_df.empty:
                logger.info("No new data to merge")
                return historical_df
            
            combined_df = pd.concat([historical_df, new_df], ignore_index=True)
            
            initial_count = len(combined_df)
            combined_df = combined_df.drop_duplicates(
                subset=['date', 'home_team', 'away_team'], 
                keep='last'
            ).reset_index(drop=True)
            
            duplicates_removed = initial_count - len(combined_df)
            
            if duplicates_removed > 0:
                logger.info(f"Removed {duplicates_removed} duplicate matches")
            
            logger.info(f"Merged dataset: {len(historical_df)} historical + {len(new_df)} new = {len(combined_df)} total")
            
            return combined_df
            
        except Exception as e:
            logger.error(f"Error merging with historical data: {e}")
            return new_df if new_df is not None else historical_df
    
    def handle_privacy_popup(self, driver: ChromeDriver, max_attempts: int = 2) -> bool:
        for attempt in range(max_attempts):
            try:
                if driver.safe_get('https://www.11v11.com/'):
                    try:
                        agree_span = WebDriverWait(driver.driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'AGREE')]"))
                        )
                        agree_span.click()
                        time.sleep(2)
                        return True
                    except TimeoutException:
                        return True
                else:
                    if attempt < max_attempts - 1:
                        time.sleep(3)
                        continue
            except Exception as e:
                logger.warning(f"Privacy popup handling error: {e}")
                if attempt < max_attempts - 1:
                    time.sleep(3)
                    continue
        
        return False
    
    def scrape_country_matches(self, country: str, season: str) -> List[Dict[str, Any]]:
        matches = []
        
        with ChromeDriver(timeout=FIFAConfig.GLOBAL_TIMEOUT) as driver:
            try:
                self.handle_privacy_popup(driver)
                
                url = f'https://www.11v11.com/teams/{country}/tab/matches/season/{season}/'
                
                if not driver.safe_get(url):
                    logger.error(f"Failed to load matches page for {country}")
                    return []
                
                time.sleep(3)
                
                page_source = driver.driver.page_source
                soup = bs.BeautifulSoup(page_source, features="lxml")
                
                table = soup.find('table', class_='sortable')
                if not table:
                    logger.warning(f"No matches table found for {country}")
                    return []
                
                rows = table.find_all('tr')[1:]
                
                for row in rows:
                    cells = row.find_all('td')
                    
                    if len(cells) >= 5:
                        date_text = cells[0].get_text(strip=True)
                        match_text = cells[1].get_text(strip=True)
                        result_text = cells[2].get_text(strip=True)
                        score_text = cells[3].get_text(strip=True)
                        competition_text = cells[4].get_text(strip=True)
                        
                        detail_url = None
                        match_link = cells[1].find('a')
                        if match_link:
                            detail_url = match_link.get('href')
                            if detail_url and not detail_url.startswith('http'):
                                detail_url = f"https://www.11v11.com{detail_url}"
                        
                        match_data = {
                            'date': date_text,
                            'match': match_text,
                            'result': result_text,
                            'score': score_text,
                            'competition': competition_text,
                            'detail_url': detail_url,
                            'country': country,
                            'season': season
                        }
                        
                        matches.append(match_data)
                
                logger.info(f"Successfully extracted {len(matches)} matches for {country}")
                
            except Exception as e:
                logger.error(f"Error scraping {country}: {e}")
                return []
        
        return matches
    
    def get_venue_details(self, detail_url: str, max_retries: int = 2) -> Tuple[Optional[str], Optional[str]]:
        if not detail_url:
            return None, None
        
        for attempt in range(max_retries):
            with ChromeDriver(timeout=FIFAConfig.DETAIL_TIMEOUT) as driver:
                try:
                    if not driver.safe_get(detail_url):
                        if attempt < max_retries - 1:
                            time.sleep(2)
                            continue
                        else:
                            break
                    
                    time.sleep(2)
                    
                    page_source = driver.driver.page_source
                    soup = bs.BeautifulSoup(page_source, features="lxml")
                    
                    venue = None
                    competition = None
                    
                    basic_data_table = soup.find('div', class_='basicData')
                    if basic_data_table:
                        table = basic_data_table.find('table')
                        if table:
                            rows = table.find_all('tr')
                            for row in rows:
                                cells = row.find_all('td')
                                if len(cells) >= 2:
                                    label = cells[0].get_text(strip=True).lower()
                                    value = cells[1].get_text(strip=True)
                                    
                                    if 'venue' in label:
                                        venue = value
                                    elif 'competition' in label:
                                        competition = value
                    
                    if not venue or not competition:
                        venue_cells = soup.find_all('td')
                        
                        for i, cell in enumerate(venue_cells):
                            cell_bold = cell.find('b')
                            if cell_bold:
                                label = cell_bold.get_text().lower()
                                if 'venue' in label and not venue:
                                    if i + 1 < len(venue_cells):
                                        venue = venue_cells[i + 1].get_text(strip=True)
                                elif 'competition' in label and not competition:
                                    if i + 1 < len(venue_cells):
                                        competition = venue_cells[i + 1].get_text(strip=True)
                    
                    if venue:
                        self.venue_tracker.add_venue_found(venue)
                        self.stats['venues_found'] += 1
                    
                    return venue, competition
                    
                except Exception as e:
                    logger.warning(f"Detail attempt {attempt + 1} failed: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(3)
        
        return None, None
    
    def determine_neutral_pitch(self, venue: str, home_fifa_code: str, away_fifa_code: str) -> Tuple[bool, str, str]:
        if not venue:
            return False, home_fifa_code, away_fifa_code
        
        venue_country = self.venue_tracker.get_venue_country(venue)
        
        if not venue_country:
            return False, home_fifa_code, away_fifa_code
        
        home_country = FIFA_CODE_TO_COUNTRY.get(home_fifa_code, home_fifa_code)
        away_country = FIFA_CODE_TO_COUNTRY.get(away_fifa_code, away_fifa_code)
        
        home_ratio = fuzz.ratio(venue_country.lower(), home_country.lower())
        away_ratio = fuzz.ratio(venue_country.lower(), away_country.lower())
        
        if home_ratio >= FIFAConfig.FUZZY_THRESHOLD:
            return False, home_fifa_code, away_fifa_code
        elif away_ratio >= FIFAConfig.FUZZY_THRESHOLD:
            return False, away_fifa_code, home_fifa_code
        else:
            self.stats['neutral_pitch_matches'] += 1
            return True, home_fifa_code, away_fifa_code
    
    def convert_team_name_to_fifa_code(self, team_name: str) -> str:
        for country_name, fifa_code in COUNTRY_TO_FIFA_CODE.items():
            if team_name.lower() == country_name.lower():
                return fifa_code
        
        team_lower = team_name.lower().strip()
        for country_name, fifa_code in COUNTRY_TO_FIFA_CODE.items():
            if len(country_name) > 3 and country_name.lower() in team_lower:
                return fifa_code
        
        return team_name[:3].upper()
    
    def parse_match_data(self, match: Dict[str, Any], country_fifa_code: str) -> Dict[str, Any]:
        try:
            date = datetime.strptime(match['date'], '%d %b %Y').strftime('%Y-%m-%d')
        except:
            date = match['date']
        
        match_str = match['match']
        if ' v ' in match_str:
            home, away = match_str.split(' v ', 1)
            home = home.strip()
            away = away.strip()
        else:
            home = away = match_str
        
        home_code = self.convert_team_name_to_fifa_code(home)
        away_code = self.convert_team_name_to_fifa_code(away)
        
        if country_fifa_code:
            if home.lower() == match['country'].lower():
                home_code = country_fifa_code
            elif away.lower() == match['country'].lower():
                away_code = country_fifa_code
        
        result = match['score'].replace('-', ':')
        pso = ''
        
        pen_pattern = r'\((\d+:\d+)\)'
        pen_match = re.search(pen_pattern, result)
        
        if pen_match:
            pso = pen_match.group(1)
            result = re.sub(pen_pattern, '', result).strip()
        
        result = re.sub(r'\s+', ' ', result).strip()
        if result.endswith('a.e.t.'):
            result = result.replace('a.e.t.', '').strip()
        
        return {
            'date': date,
            'home_team': home_code,
            'away_team': away_code,
            'result': result,
            'pso': pso,
            'competition': match['competition'],
            'neutral_pitch': False
        }
    
    def scrape_countries_batch(self, countries: List[str], season: str = '2025') -> List[Dict[str, Any]]:
        batch_matches = []
        
        for i, country in enumerate(countries):
            logger.info(f"Processing country {i+1}/{len(countries)} in batch: {country}")
            
            country_fifa_code = URL_NAME_TO_FIFA_CODE.get(country, country[:3].upper())
            
            matches = None
            for attempt in range(FIFAConfig.MAX_RETRIES):
                if attempt > 0:
                    logger.info(f"Retry attempt {attempt + 1} for {country}")
                    ChromeProcessManager.kill_all_chrome_processes()
                    time.sleep(5)
                
                try:
                    matches = self.scrape_country_matches(country, season)
                    if matches:
                        break
                except Exception as e:
                    logger.error(f"Scraping attempt failed for {country}: {e}")
                    ChromeProcessManager.kill_all_chrome_processes()
            
            if not matches:
                logger.error(f"Failed to scrape {country} after {FIFAConfig.MAX_RETRIES} attempts")
                self.stats['failed_countries'].append(country)
                continue
            
            self.stats['successful_countries'].append(country)
            
            country_processed_matches = 0
            for j, match in enumerate(matches):
                try:
                    allgames_match = self.parse_match_data(match, country_fifa_code)
                    
                    if match['detail_url']:
                        try:
                            venue, detailed_competition = self.get_venue_details(match['detail_url'])
                            
                            if venue:
                                neutral_pitch, final_home, final_away = self.determine_neutral_pitch(
                                    venue, allgames_match['home_team'], allgames_match['away_team']
                                )
                                
                                allgames_match['neutral_pitch'] = neutral_pitch
                                
                                if final_home != allgames_match['home_team'] or final_away != allgames_match['away_team']:
                                    allgames_match['home_team'] = final_home
                                    allgames_match['away_team'] = final_away
                                    
                                    if ':' in allgames_match['result']:
                                        score_parts = allgames_match['result'].split(':')
                                        if len(score_parts) == 2:
                                            allgames_match['result'] = f"{score_parts[1]}:{score_parts[0]}"
                                    
                                    if allgames_match['pso'] and ':' in allgames_match['pso']:
                                        pso_parts = allgames_match['pso'].split(':')
                                        if len(pso_parts) == 2:
                                            allgames_match['pso'] = f"{pso_parts[1]}:{pso_parts[0]}"
                            
                            if detailed_competition:
                                allgames_match['competition'] = detailed_competition
                                
                        except Exception as e:
                            logger.warning(f"Venue processing error for match {j+1}: {e}")
                    
                    batch_matches.append(allgames_match)
                    country_processed_matches += 1
                    
                    if j < len(matches) - 1:
                        time.sleep(FIFAConfig.RATE_LIMIT_DELAY)
                        
                except Exception as e:
                    logger.error(f"Match processing error: {e}")
                    continue
            
            logger.info(f"{country.upper()}: {country_processed_matches}/{len(matches)} matches processed")
            
            ChromeProcessManager.kill_all_chrome_processes()
            if i < len(countries) - 1:
                time.sleep(5)
        
        return batch_matches
    
    def scrape_data(self):
        try:
            with PerformanceTimer(f"FIFA scraping"):
                
                historical_df, last_date = self.load_historical_data()
                
                if historical_df is None or last_date is None:
                    raise Exception("Could not load historical data from AllGames.csv - file may be corrupted")
                
                logger.info(f"Comprehensive data collection mode - minimal filtering")
                logger.info(f"Historical data: {len(historical_df)} matches, last date: {last_date}")
                logger.info(f"Starting FIFA scrape for {len(FIFA_COUNTRIES_11V11)} countries")
                
                ChromeProcessManager.kill_all_chrome_processes()
                
                all_matches = []
                
                total_batches = (len(FIFA_COUNTRIES_11V11) + FIFAConfig.BATCH_SIZE - 1) // FIFAConfig.BATCH_SIZE
                
                for batch_idx in range(0, len(FIFA_COUNTRIES_11V11), FIFAConfig.BATCH_SIZE):
                    batch_num = (batch_idx // FIFAConfig.BATCH_SIZE) + 1
                    batch_countries = FIFA_COUNTRIES_11V11[batch_idx:batch_idx + FIFAConfig.BATCH_SIZE]
                    
                    logger.info(f"Processing batch {batch_num}/{total_batches}: {len(batch_countries)} countries")
                    
                    with PerformanceTimer(f"batch {batch_num}"):
                        ChromeProcessManager.kill_all_chrome_processes()
                        
                        batch_matches = self.scrape_countries_batch(batch_countries, str(self.season_year))
                        
                        all_matches.extend(batch_matches)
                        
                        logger.info(f"Batch {batch_num} completed: {len(batch_matches)} matches collected")
                        
                        ChromeProcessManager.kill_all_chrome_processes()
                        
                        if batch_num < total_batches:
                            time.sleep(10)
                
                ChromeProcessManager.kill_all_chrome_processes()
                
                self.venue_tracker.save_all_venue_files()
                
                logger.info(f"Pre-filter: {len(all_matches)} total matches scraped")
                filtered_matches = self.filter_new_matches(all_matches, last_date)
                logger.info(f"Post-filter: {len(filtered_matches)} matches kept")
                
                new_matches_df = pd.DataFrame(filtered_matches)
                
                if not new_matches_df.empty:
                    new_matches_df['date'] = pd.to_datetime(new_matches_df['date'])
                    new_matches_df = new_matches_df.sort_values('date').reset_index(drop=True)
                    new_matches_df['date'] = new_matches_df['date'].dt.strftime('%Y-%m-%d')
                
                final_df = self.merge_with_historical(new_matches_df, historical_df)
                self.save_complete_data(final_df)
                
                self.stats['total_matches'] = len(final_df)
                
                metadata = {
                    'scraper_type': 'FIFA',
                    'season_year': self.season_year,
                    'incremental': True,
                    'last_historical_date': last_date,
                    'historical_matches': len(historical_df),
                    'new_matches': len(new_matches_df),
                    'total_matches': self.stats['total_matches'],
                    'total_countries': self.stats['total_countries'],
                    'successful_countries': len(self.stats['successful_countries']),
                    'failed_countries': len(self.stats['failed_countries']),
                    'venues_found': self.stats['venues_found'],
                    'neutral_pitch_matches': self.stats['neutral_pitch_matches'],
                    'failed_venues_count': len(self.venue_tracker.failed_venues),
                    'success_rate': len(self.stats['successful_countries'])/self.stats['total_countries']*100,
                    'success': True
                }
                
                logger.info(f"FIFA incremental scraping completed:")
                logger.info(f"- Historical: {metadata['historical_matches']} matches")
                logger.info(f"- New: {metadata['new_matches']} matches") 
                logger.info(f"- Total: {metadata['total_matches']} matches")
                logger.info(f"- Venues found: {metadata['venues_found']}")
                logger.info(f"- Failed venues: {metadata['failed_venues_count']} (saved for manual mapping)")
                
                return final_df, metadata
                
        except Exception as e:
            empty_df = pd.DataFrame(columns=['index''date', 'home_team', 'away_team', 'result', 'pso', 'competition', 'neutral_pitch'])
            error_metadata = {
                'scraper_type': 'FIFA',
                'season_year': self.season_year,
                'incremental': True,
                'total_matches': 0,
                'total_countries': self.stats['total_countries'],
                'successful_countries': 0,
                'failed_countries': 0,
                'venues_found': 0,
                'neutral_pitch_matches': 0,
                'failed_venues_count': 0,
                'success_rate': 0,
                'success': False,
                'error': str(e)
            }
            logger.error(f"FIFA scraping failed: {e}")
            ChromeProcessManager.kill_all_chrome_processes()
            return empty_df, error_metadata


def get_epl_season_year():
    return EPL_CONFIG.get_season_year()


def main():
    logger.info("Testing FIFA Scraper")
    fifa_scraper = FIFAScraper()
    
    try:
        fifa_df, fifa_meta = fifa_scraper.scrape_data()
        logger.info(f"FIFA scraping completed: {len(fifa_df)} matches, Success rate: {fifa_meta.get('success_rate', 0):.1f}%")
        
    except Exception as e:
        logger.error(f"FIFA Error: {e}")
    finally:
        ChromeProcessManager.kill_all_chrome_processes()


if __name__ == "__main__":
    main()