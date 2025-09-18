import os
import json
import requests
import argparse
from jinja2 import Environment, FileSystemLoader
from datetime import datetime
from dotenv import load_dotenv

# --- CONFIGURATION ---
# Load environment variables from .env file
load_dotenv() 

# The script will now prioritize an API key from .env, but still works with gcloud ADC
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

def get_api_url():
    """Constructs the API URL. For local dev, we assume gemini-pro."""
    # Note: If using ADC, you'd typically use the Google Cloud client libraries
    # which handle authentication automatically. For a direct REST API call,
    # an API key is the most straightforward method shown here.
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not found. Please set it in your .env file or environment.")
    return f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={GEMINI_API_KEY}"

# --- PROMPT & JSON SCHEMA DEFINITION ---
# This "brain" remains the same.
SYSTEM_PROMPT = """
You are a world-class financial analyst. Your task is to conduct comprehensive research on a given company ticker and generate a structured, data-driven, one-page investment report in JSON format. The report must be objective, factual, and backed by recent data (assume today's date is September 18, 2025).

The report must cover three main areas:
1.  **Foundational Strength & Story:** The company's moat, leadership, business model, and risks.
2.  **Financial Health:** The strength of the balance sheet, revenue quality, and profitability.
3.  **Growth & Market Position:** Customer validation, market opportunity (TAM), and competitive landscape.

For each of these areas, provide 3-4 specific metrics, each with a score from 1.0 to 10.0, a letter grade (a, b, c, d, f), and concise reasoning. Also, generate data for four financial charts.

The final JSON output MUST strictly adhere to the provided schema.
"""

JSON_SCHEMA = {
    "type": "OBJECT",
    "properties": { "company_name": {"type": "STRING"}, "ticker": {"type": "STRING"}, "overall_score": {"type": "NUMBER", "description": "The final aggregate score, calculated as the average of all individual metric scores, rounded to one decimal place."}, "summary": { "type": "OBJECT", "properties": { "aggregate": {"type": "STRING", "description": "A concise, one-sentence summary of the investment thesis."}, "bull_case": {"type": "STRING", "description": "A short paragraph on the primary reasons to invest."}, "bear_case": {"type": "STRING", "description": "A short paragraph on the primary risks and counter-arguments."} } }, "scores": { "type": "OBJECT", "properties": { "foundational": { "type": "ARRAY", "items": {"$ref": "#/definitions/score_item"} }, "financial": { "type": "ARRAY", "items": {"$ref": "#/definitions/score_item"} }, "growth": { "type": "ARRAY", "items": {"$ref": "#/definitions/score_item"} } } }, "charts": { "type": "OBJECT", "properties": { "chart1": {"$ref": "#/definitions/chart_object"}, "chart2": {"$ref": "#/definitions/chart_object"}, "chart3": {"$ref": "#/definitions/chart_object"}, "chart4": {"$ref": "#/definitions/chart_object"} } } },
    "definitions": { "score_item": { "type": "OBJECT", "properties": { "metric": {"type": "STRING"}, "score": {"type": "NUMBER"}, "grade": {"type": "STRING", "enum": ["a", "b", "c", "d", "f"]}, "reasoning": {"type": "STRING"} } }, "chart_object": { "type": "OBJECT", "properties": { "title": {"type": "STRING"}, "type": {"type": "STRING", "enum": ["bar", "line"]}, "labels": {"type": "ARRAY", "items": {"type": "STRING"}}, "datasets": { "type": "ARRAY", "items": { "type": "OBJECT", "properties": { "label": {"type": "STRING"}, "data": {"type": "ARRAY", "items": {"type": "NUMBER"}}, "backgroundColor": {"type": "STRING"}, "borderColor": {"type": "STRING"}, "fill": {"type": "BOOLEAN"}, "tension": {"type": "NUMBER"} } } }, "yAxisFormatter": {"type": "STRING", "description": "A JavaScript function body as a string, e.g., 'return `$${value}M`;'"} } } }
}

def generate_report_data(ticker, api_url):
    """Calls the Gemini API to get the structured financial report data."""
    print(f"▶️ Starting analysis for ticker: {ticker}...")
    
    user_prompt = f"Generate a complete investment report for the company with the ticker: ${ticker}"
    
    payload = { "contents": [{"parts": [{"text": user_prompt}]}], "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]}, "generationConfig": { "responseMimeType": "application/json", "responseSchema": JSON_SCHEMA } }
    
    response = requests.post(api_url, json=payload, headers={"Content-Type": "application/json"})
    
    if response.status_code != 200:
        raise Exception(f"API Error: {response.status_code}\n{response.text}")
        
    response_json = response.json()
    
    try:
        report_text = response_json['candidates'][0]['content']['parts'][0]['text']
        report_data = json.loads(report_text)
        print("✅ Successfully received and parsed report data from Gemini.")
        return report_data
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        print("❌ Error parsing Gemini response:")
        print(response_json)
        raise e

def render_html_report(data):
    """Renders the HTML template with the report data."""
    print(f"📄 Rendering HTML report for {data['ticker']}...")
    # Use absolute paths for reliability
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    env = Environment(loader=FileSystemLoader(project_root))
    template = env.get_template('template.html')
    
    data['generation_date'] = datetime.now().strftime("%B %d, %Y")
    
    output_html = template.render(data)
    
    output_path = os.path.join(project_root, 'reports', f"{data['ticker']}.html")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding='utf-8') as f:
        f.write(output_html)
    print(f"✅ Report saved to {output_path}")

def update_report_index(new_report_data, project_root):
    """Updates the reports.json file with the new report info."""
    index_path = os.path.join(project_root, 'reports.json')
    index_data = {'reports': []}
    
    if os.path.exists(index_path):
        with open(index_path, 'r') as f:
            try: index_data = json.load(f)
            except json.JSONDecodeError: print("⚠️ Warning: reports.json is corrupted. Starting fresh.")

    index_data['reports'] = [r for r in index_data.get('reports', []) if r.get('ticker') != new_report_data['ticker']]
    index_data['reports'].append({ 'ticker': new_report_data['ticker'], 'name': new_report_data['company_name'] })
    
    with open(index_path, 'w') as f:
        json.dump(index_data, f, indent=2)
    print(f"✅ Updated {index_path}")

def main():
    """Main function to run the report generation from the command line."""
    parser = argparse.ArgumentParser(description="Generate a financial report for a given company ticker.")
    parser.add_argument("ticker", type=str, help="The company stock ticker symbol (e.g., NVDA, GOOGL).")
    args = parser.parse_args()
    
    api_url = get_api_url()
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    report_data = generate_report_data(args.ticker, api_url)
    render_html_report(report_data)
    update_report_index(report_data, project_root)
    print("\n🎉 Process completed successfully!")

if __name__ == "__main__":
    main()
