import requests
from bs4 import BeautifulSoup
import time
import random
import json

recipes_data_file_path = "data/recipes_data.json"

def get_headers():
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    }

def make_request(url, max_retries=3):
    for attempt in range(max_retries):
        try:
            time.sleep(random.uniform(1, 3))
            response = requests.get(url, headers=get_headers(), timeout=10)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            if attempt == max_retries - 1:
                raise e
            time.sleep(random.uniform(2, 5))
    return None

def parse_recipe_links():
    all_recipe_links = set()
    
    category_urls = [
        "https://eda.ru/recepty/vypechka-deserty",
        "https://eda.ru/recepty/zavtraki",
        "https://eda.ru/recepty/osnovnye-blyuda",
        "https://eda.ru/recepty/salaty",
        "https://eda.ru/recepty/pasta-picca",
        "https://eda.ru/recepty/supy",
        "https://eda.ru/recepty/zakuski",
        "https://eda.ru/recepty/sendvichi"
    ]
    
    for category_url in category_urls:
        page = 1
        while True:
            try:
                paginated_url = f"{category_url}?page={page}"
                
                response = make_request(paginated_url)
                if not response:
                    break
                
                soup = BeautifulSoup(response.text, 'html.parser')
                cards = soup.find_all('div', class_='emotion-n1x91l') # Изменено!
                
                if not cards:
                    break
                
                new_links = 0
                for card in cards:
                    link = card.find('a', href=True)
                    if link:
                        full_url = "https://eda.ru" + link['href'] if not link['href'].startswith('http') else link['href']
                        if full_url not in all_recipe_links:
                            all_recipe_links.add(full_url)
                            new_links += 1
                
                if len(all_recipe_links) > 150:
                    break                
                
                page += 1
                
            except Exception as e:
                break
    
    return list(all_recipe_links)

def parse_nutrition_info(soup):
    nutrition_info = {
        "calories": "Не указано",
        "proteins": "Не указано",
        "fats": "Не указано",
        "carbs": "Не указано"
    }
    
    try:
        # Find the nutrition container
        nutrition_container = soup.find('span', {'itemprop': 'nutrition', 'itemtype': 'http://schema.org/NutritionInformation'})
        
        if nutrition_container:
            # Parse calories
            calories_elem = nutrition_container.find('span', {'itemprop': 'calories'})
            if calories_elem:
                nutrition_info["calories"] = calories_elem.text.strip()
            
            # Parse other nutritional values from the emotion-16si75h containers
            nutrition_divs = nutrition_container.find_all('div', class_='emotion-16si75h')
            
            if len(nutrition_divs) >= 3:
                proteins_value = nutrition_divs[0].text.strip()
                fats_value = nutrition_divs[1].text.strip()
                carbs_value = nutrition_divs[2].text.strip()
                
                nutrition_info.update({
                    "proteins": proteins_value,
                    "fats": fats_value,
                    "carbs": carbs_value
                })
    
    except Exception as e:
        pass
        
    return nutrition_info

# Исправить парсинг шагов приготовления и ингридиентов
def parse_recipe_details(recipe_url):
    """Parse details from an individual recipe page with improved error handling"""
    try:
        response = make_request(recipe_url)
        if not response:
            return None
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract title with fallback
        title_elem = soup.find('h1', class_='emotion-gl52ge')
        if not title_elem:
            raise ValueError("Title element not found")
        title = title_elem.text.strip()
        
        # Extract portions and cooking time with proper error handling
        portions = "Не указано"
        cooking_time = "Не указано"
        
        portions_elem = soup.find('div', class_='emotion-1047m5l')
        if portions_elem:
            portions = portions_elem.text.strip()
            
        time_elem = soup.find('div', class_='emotion-my9yfq')
        if time_elem:
            cooking_time = time_elem.text.strip()
        
        # Get ingredients from multiple blocks
        ingredients = []
        # Найти все контейнеры с ингредиентами
        ingredient_containers = soup.find_all('div', class_='emotion-1oyy8lz')
        if ingredient_containers:
            for container in ingredient_containers:
                # В каждом контейнере найти элементы ингредиентов
                ingredient_items = container.find_all('div', class_='emotion-ydhjlb')
                for item in ingredient_items:
                    # Найти название ингредиента
                    name_elem = item.find('span', itemprop='recipeIngredient')
                    # Найти количество
                    quantity_elem = item.find('span', class_='emotion-bsdd3p')

                    # Обработка текста для каждого ингредиента
                    name = name_elem.text.strip() if name_elem else "Неизвестный ингредиент"
                    quantity = quantity_elem.text.strip() if quantity_elem else "Количество не указано"

                    # Добавить в общий список ингредиентов
                    ingredients.append(f"{name}: {quantity}")
        
        # Parse nutrition information
        nutrition_info = parse_nutrition_info(soup)
        
        return {
            "title": title,
            "url": recipe_url,
            "portions": portions,
            "cooking_time": cooking_time,
            "ingredients": ingredients,
            "nutrition": nutrition_info
        }
        
    except Exception as e:
        return None

   
def get_recipes():
    recipe_links = parse_recipe_links()
    
    if not recipe_links:
        return
    
    recipes = []
    for i, link in enumerate(recipe_links, 1):
        recipe = parse_recipe_details(link)
        if recipe:
            recipes.append(recipe)
            
    return recipes

def load_recipes():
    try:
        with open(recipes_data_file_path, "r") as f:
            recipes = json.load(f)
    except:
        recipes = get_recipes()
        with open(recipes_data_file_path, "w") as f:
            json.dump(recipes, f)
        
    return recipes

if __name__ == "__main__":
    print("Начал загрузку рецептов!!")
    recipes = get_recipes()
    print("Загрузил рецепты")
    with open(recipes_data_file_path, "w") as f:
        json.dump(recipes, f)
        print("Сохранил рецепты")