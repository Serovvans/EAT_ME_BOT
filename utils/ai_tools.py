import os
import re

from langchain_community.chat_models.gigachat import GigaChat
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain.memory import ConversationBufferMemory
from langchain_core.documents import Document
from langchain_chroma import Chroma
from langchain_gigachat.embeddings import GigaChatEmbeddings

from utils.parse_recipies import load_recipes

def get_docs_for_db():
    documents = []
    
    recipes = load_recipes()
    valid_recipes = [r for r in recipes if r is not None]
    for recipe in valid_recipes:
        
        document = f"{recipe['title']}\n\n" \
                      f"Ингредиенты:\n" + "\n".join(recipe['ingredients']) + "\n\n"\
                      f"Порции: {recipe['portions']}\n" \
                      f"Время приготовления: {recipe['cooking_time']}\n\n" \
                      f"Пищевая ценность:\n" \
                      f"Калории: {recipe['nutrition']['calories']}\n" \
                      f"Белки: {recipe['nutrition']['proteins']}\n" \
                      f"Жиры: {recipe['nutrition']['fats']}\n" \
                      f"Углеводы: {recipe['nutrition']['carbs']}\n\n" \
                    
        documents.append(
            Document(page_content=document, metadata={"source": recipe['url']})
        )

    return documents

vectorstore = Chroma.from_documents(
    get_docs_for_db(),
    embedding = GigaChatEmbeddings(
    credentials=os.getenv("GIGACHAT_KEY"), scope="GIGACHAT_API_PERS", verify_ssl_certs=False
    ),
)

# Инициализация GigaChat
llm = GigaChat(
    credentials=os.getenv("GIGACHAT_KEY"),
    model='GigaChat:latest',
    verify_ssl_certs=False,
    temperature=0.3,
    top_p=0.1,
)

# Работа с памятью для каждого пользователя отдельно
user_memories = {}

def get_user_memory(user_id):
    if user_id not in user_memories:
        user_memories[user_id] = ConversationBufferMemory(memory_key="history")
    return user_memories[user_id]

# Шаг 1: Генерация описаний приемов пищи
def generate_meal_descriptions(user_info, new_prompt=""):
    template = """
    {history}
    Ты — помощник по планированию питания.
    Твоя задача — составить список из ровно 10 блюд, которые подойдут пользователю, учитывая:  
    1. Личную информацию о пользователе и его цели по питанию: {about_user}.  
    2. Запрещенные продукты: {forbidden_products}.  
    3. Любимые продукты: {favorite_products}.  
    4. Предпочтения в готовке (время, бюджет, цели): {cooking_preferences}.  

    - Новые требования пользователя: {new_prompt}.  

    **Формат ответа:**  
    Список блюд, каждое на отдельой строке. Одним списоком, без лишних вступлений и текста.
    Пример:  
    Овсянка с ягодами и медом , Тушеные овощи с курицей , Салат Цезарь...  
    """

    prompt = PromptTemplate(template=template, input_variables=[
        "history", "about_user", "forbidden_products", "favorite_products", "cooking_preferences",
        "new_prompt", "curr_plan_state", "day"])
    memory = get_user_memory(user_info['user_id'])
    chain = LLMChain(llm=llm, prompt=prompt)
    
    response = chain.run({
        "about_user": user_info['about_user'],
        "forbidden_products": user_info['forbidden_products'],
        "favorite_products": user_info['favorite_products'],
        "cooking_preferences": user_info['cooking_preferences'],
        "new_prompt": new_prompt,
        "history": memory.load_memory_variables({})["history"],
    })
    if new_prompt:
        memory.save_context({"input": new_prompt}, {"output": response})
    else:
        memory.save_context({"input":
        f"{user_info['about_user']}, {user_info['forbidden_products']}, {user_info['favorite_products']}, {user_info['cooking_preferences']}"},
                            {"output": response})
    
    return response

# Шаг 2: Поиск рецептов
def find_recipes(query):
    query = query[:512]
    results = vectorstore.similarity_search_with_score(query)

    top_results = results[:1]

    top_texts = [doc.page_content for doc, score in top_results]

    result_string = "; ".join(top_texts)
    return result_string

# Шаг 3: Генерация итогового плана
def generate_final_plan(recipes, user_info, days, current_state=""):
    template = """
    Ты — профессиональный помощник по планированию питания. Составь итоговый план питания на дни {days}, строго соответствуя следующим условиям.
    ### Условия:
    1. **Используй только новые блюда:** *Не используй блюда, которые уже были включены в предыдущие дни*:  
    {current_state}  

    2. **Единые приемы пищи:** Каждый прием пищи (завтрак, обед, ужин) должен быть одинаковым для всех дней, чтобы минимизировать затраты времени на приготовление и планирование.  

    3. **Рецепты:**  
    - Используй предложенные готовые рецепты, если они подходят:  
    {recipes}  
    - Если готовые рецепты не подходят, предложи свои варианты.  

    4. **Формат ответа:**  
    - Весь план на указанные дни описывается одним блоком (без разделения на отдельные дни).  
    - Список дней оформляется как заголовок.  
    - Каждый прием пищи оформляется как подзаголовок.  
    - Для каждого блюда укажи:  
        - Название блюда.  
        - Краткое описание рецепта (2-3 предложения).  
        - Ингредиенты с указанием количества.  
        - Калорийность и разбивку по БЖУ (белки, жиры, углеводы).  

    ### Пример ответа:
    {days}:  
    **Завтрак:**  
    Овсянка с бананом и орехами  
    Смешать овсянку с молоком, нарезать банан, добавить мед и орехи. Разогреть в микроволновке 2 минуты.  
    Ингредиенты: ["Овсянка - 100 г", "Молоко - 200 мл", "Банан - 1 шт", "Мед - 1 ч.л.", "Орехи грецкие - 20 г"]  
    Калории: 370, Белки: 12 г, Жиры: 9 г, Углеводы: 60 г  

    **Обед:**  
    Куриное филе с киноа и овощами  
    Отварить киноа, обжарить куриное филе, приготовить овощи (брокколи, морковь) на пару. Смешать все в тарелке.  
    Ингредиенты: ["Куриное филе - 200 г", "Киноа - 100 г", "Брокколи - 150 г", "Морковь - 100 г"]  
    Калории: 450, Белки: 35 г, Жиры: 10 г, Углеводы: 50 г  

    **Ужин:**  
    Салат с тунцом и яйцом  
    Смешать салатные листья, консервированный тунец, вареные яйца, добавить оливковое масло и лимонный сок.  
    Ингредиенты: ["Салатные листья - 100 г", "Тунец консервированный - 150 г", "Яйца - 2 шт", "Оливковое масло - 1 ст.л.", "Лимонный сок - 1 ч.л."]  
    Калории: 320, Белки: 30 г, Жиры: 18 г, Углеводы: 5 г  

    План на {days} готов.
    """

    prompt = PromptTemplate(template=template, input_variables=["recipes", "cooking_preferences", "current_state", "days"])
    chain = LLMChain(llm=llm, prompt=prompt)
    
    response = chain.run({"recipes": recipes, "cooking_preferences": user_info['cooking_preferences'],
                          "current_state": current_state, "days": ", ".join(days)})
    
    return response

# Шаг 4: Генерация графика закупок и готовки
def generate_shopping_schedule(user_info, meal_plan, days, current_state=""):
    template = """
    Ты — профессиональный помощник по планированию питания. Составь график закупок и готовки на дни {days}, строго следуя этим условиям.

    ### Исходные данные:
    План питания:  
    {meal_plan}  

    ### Требования к графику:
    1. **Оптимизация готовки:** Готовь блюда в таких объемах, чтобы их хватало на несколько дней.
    2. **Готовка и закупка** всех продуктов проходит в один день и один раз - в первый из указанных дней. 
    2. **Оформление:**  
    - Нужно описать общий список покупок и готовки, он будт произведен в перый из указанных дней.  
    - Список дней оформляется как заголовок.  
    3. **Разделы:**  
    - Список продуктов для закупки (Продукт — количество).  
    - Список блюд для приготовления (Название блюда, Краткий рецепт).
    4. **Ответ должен быть краткий**. В краткой форме должна быть изложена необходимая информация

    ### Пример ответа:
    {days}:  
    **Список продуктов:**  
    - Яблоки — 10 шт.  
    - Молоко — 2 л.  
    - Овсянка — 500 г.  
    - Куриного филе — 1 кг.  

    **Список блюд:**  
    - **Овсянка с ягодами**  
    Рецепт: Смешать овсянку с молоком и свежими ягодами, оставить настояться 10 минут. Готовить сразу на 3 дня.  
    - **Курица с овощами**  
    Рецепт: Замариновать куриное филе, обжарить с овощами (морковь, брокколи, перец). Разделить на порции, хватит на 4 дня.  

    Расписание на {days} готово!
    """
    
    prompt = PromptTemplate(template=template, input_variables=["meal_plan", "cooking_preferences", "coocking_plan_format",
                                                                "days", "current_state"])
    chain = LLMChain(llm=llm, prompt=prompt)
    
    response = chain.run({"meal_plan": meal_plan, "cooking_preferences": user_info['cooking_preferences'],
                      "current_state": current_state, "days": ", ".join(days)})

    
    return response


def analyze_cooking_preferences_with_llm(cooking_preferences, llm):
    template = """
    Ты — эксперт по питанию. Пользователь описал свои предпочтения в готовке:  
    "{cooking_preferences}".  

    Ответь кратко:  
    - Сколько дней в неделю пользователь хочет готовить?  
    - Сколько минут он готов тратить на готовку?  

    **Формат ответа:**  
    Дни готовки: X; Время готовки: Y минут.  
    """
    
    prompt = PromptTemplate(template=template, input_variables=["cooking_preferences"])
    chain = LLMChain(llm=llm, prompt=prompt)
    response = chain.run({"cooking_preferences": cooking_preferences})

    # Парсим ответ LLM
    match = re.search(r"Дни готовки: (\d+); Время готовки: (\d+) минут", response)
    cooking_days = int(match.group(1)) if match else 3  # Значение по умолчанию
    max_cooking_time = int(match.group(2)) if match else 120  # Значение по умолчанию
    return cooking_days, max_cooking_time

def create_meal_and_coocking_plan(id, user_info, prompt=""):
    days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    user_info['user_id'] = id

    # Анализируем предпочтения пользователя
    cooking_days, max_cooking_time = analyze_cooking_preferences_with_llm(user_info["cooking_preferences"], llm)
    cooking_block_size = 7 // cooking_days  # Размер блока в днях

    meals_description = generate_meal_descriptions(user_info=user_info, new_prompt=prompt)
    recipes_descr = list(meals_description.split("\n"))

    recipes = "\n".join([find_recipes(descr + f"Готовить не более {max_cooking_time} минут") for descr in recipes_descr])

    final_plan = []
    shopping_schedule = []

    # Разбиваем дни на блоки
    for i in range(0, len(days) - (7 % cooking_days), cooking_block_size):
        if i + cooking_block_size >= len(days) - (7 % cooking_days):
            block_days = days[i:]
        else:
            block_days = days[i:i + cooking_block_size]
            
        block_plan = []
        block_shopping = []

        block_plan = generate_final_plan(recipes=recipes, user_info=user_info, days=block_days, current_state="\n".join(final_plan))

        block_shopping = generate_shopping_schedule(user_info, block_plan, days=block_days, current_state="\n".join(shopping_schedule))

        final_plan.append(block_plan)
        shopping_schedule.append(block_shopping)

    return final_plan, shopping_schedule
