// Generated from config/category-rules.json by scripts/build_category_rules.py.
export const categoryRules = {
  "known": {
    "creature-horror": [
      348,
      679,
      1091,
      9362,
      5876,
      9392,
      300668
    ],
    "dystopian": [
      76341,
      78,
      339846,
      9693,
      110415,
      7299,
      70160,
      254320,
      9314
    ],
    "psychological-horror": [
      493922,
      530385,
      310131,
      694,
      242224,
      270303,
      44214
    ],
    "body-horror": [
      1091,
      9426,
      837,
      933260,
      630240,
      393519,
      300668
    ],
    "folklore-horror": [
      310131,
      530385
    ]
  },
  "keywords": {
    "creature-horror": [
      "creature feature",
      "creature horror",
      "monster movie",
      "monster",
      "giant monster",
      "werewolf",
      "vampire",
      "zombie",
      "killer animal",
      "alien infestation"
    ],
    "dystopian": [
      "dystopia",
      "dystopian",
      "totalitarian regime",
      "post-apocalyptic future",
      "post-apocalyptic society",
      "post-apocalyptic world"
    ],
    "psychological-horror": [
      "psychological horror",
      "psychological thriller"
    ],
    "body-horror": [
      "body horror",
      "body transformation"
    ],
    "folklore-horror": [
      "folk horror",
      "folklore horror",
      "pagan cult",
      "paganism",
      "folk tale"
    ]
  },
  "phrases": {
    "creature-horror": [
      "creature horror",
      "creature feature",
      "хоррор о монстрах"
    ],
    "dystopian": [
      "dystopian",
      "dystopia",
      "антиутопия",
      "антиутопической",
      "антиутопический"
    ],
    "psychological-horror": [
      "psychological horror",
      "психологический хоррор",
      "психологические ужасы"
    ],
    "body-horror": [
      "body horror",
      "боди хоррор",
      "телесный хоррор"
    ],
    "folklore-horror": [
      "folk horror",
      "folklore horror",
      "фолк хоррор",
      "фольклорный хоррор"
    ]
  },
  "selection": {
    "minimum_year": 2000,
    "excluded_genres": [
      99,
      10749,
      18,
      28
    ],
    "always_excluded_genres": [
      99,
      16,
      10751
    ],
    "allow_target_mixed_genres": true,
    "excluded_countries": [
      "CN",
      "HK",
      "TW",
      "JP",
      "KR",
      "IN"
    ],
    "excluded_languages": [
      "zh",
      "cn",
      "yue",
      "ja",
      "ko",
      "hi",
      "te",
      "ta",
      "ml",
      "kn",
      "bn",
      "mr",
      "gu",
      "pa"
    ],
    "require_target": true,
    "production": {
      "minimum_known_budget_usd": 3000000,
      "excluded_keywords": [
        "independent film",
        "low budget",
        "microbudget",
        "micro budget",
        "mockbuster",
        "campy",
        "parody",
        "spoof",
        "horror spoof",
        "so bad it's good"
      ],
      "popularity_weight": 4,
      "votes_weight": 1,
      "budget_weight": 2,
      "budget_scale_usd": 5000000,
      "require_known_budget": true,
      "excluded_genre_combinations": [
        [
          27,
          35
        ]
      ],
      "focus_reference_titles": [
        {
          "title": "The Witch",
          "year": 2015,
          "director": "Robert Eggers"
        },
        {
          "title": "The Lighthouse",
          "year": 2019,
          "director": "Robert Eggers"
        },
        {
          "title": "Nosferatu",
          "year": 2024,
          "director": "Robert Eggers"
        },
        {
          "title": "The Last Voyage of the Demeter",
          "year": 2023,
          "director": "André Øvredal"
        }
      ],
      "style_groups": [
        [
          "gothic",
          "gothic horror",
          "folk horror",
          "folklore horror",
          "paganism",
          "pagan cult"
        ],
        [
          "period piece",
          "17th century",
          "18th century",
          "19th century",
          "1830s",
          "1890s",
          "puritan",
          "english colony"
        ],
        [
          "isolation",
          "paranoia",
          "hallucination",
          "psychological horror",
          "psychological thriller",
          "religion",
          "religious fanaticism",
          "claustrophobia"
        ]
      ],
      "default_interests": {
        "version": 1,
        "genrePriority": [
          "horror",
          "dystopian"
        ],
        "directors": [
          {
            "name": "Роберт Эггерс",
            "aliases": [
              "Robert Eggers",
              "Роберт Эггерс"
            ]
          },
          {
            "name": "Зак Креггер",
            "aliases": [
              "Zach Cregger",
              "Зак Креггер"
            ]
          },
          {
            "name": "Дэвид Роберт Митчелл",
            "aliases": [
              "David Robert Mitchell",
              "Дэвид Роберт Митчелл"
            ]
          },
          {
            "name": "Корали Фаржа",
            "aliases": [
              "Coralie Fargeat",
              "Корали Фаржа"
            ]
          },
          {
            "name": "Андре Эвредал",
            "aliases": [
              "André Øvredal",
              "Андре Эвредал"
            ]
          }
        ]
      }
    }
  },
  "keyword_groups": {
    "creature-horror": [
      [
        "alien",
        "creature feature"
      ]
    ],
    "psychological-horror": [
      [
        "paranoia",
        "hallucination"
      ],
      [
        "psychological",
        "horror"
      ]
    ],
    "body-horror": [
      [
        "mutation",
        "body mutilation"
      ],
      [
        "body transformation",
        "horror"
      ]
    ],
    "folklore-horror": [
      [
        "ritual",
        "paganism"
      ],
      [
        "cult",
        "folk horror"
      ]
    ]
  }
};
