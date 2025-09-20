import os
import logging
import math
import requests
from io import BytesIO
from PIL import Image, ImageEnhance
from flask import Flask, request, send_file, Response

# Configurações
LOGO_FILENAME = "logo.png"  # Nome do arquivo da logo na mesma pasta
WATERMARK_OPACITY = 0.8  # Transparência (0.0 a 1.0)
ROTATION_ANGLE = 45  # Ângulo de rotação (45 graus para diagonal)
WATERMARK_SCALE = 0.20  # Escala da logo (20% da imagem)

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

def check_logo():
    """Verifica se a logo existe na pasta"""
    if not os.path.exists(LOGO_FILENAME):
        logger.error(f"Arquivo da logo '{LOGO_FILENAME}' não encontrado!")
        return False
    
    try:
        # Testar se é uma imagem válida
        with Image.open(LOGO_FILENAME) as img:
            img.verify()
        return True
    except Exception as e:
        logger.error(f"Logo inválida: {e}")
        return False

def download_image(image_url):
    """Baixa a imagem da URL"""
    try:
        response = requests.get(image_url, timeout=30)
        response.raise_for_status()
        return Image.open(BytesIO(response.content))
    except Exception as e:
        logger.error(f"Erro ao baixar imagem: {e}")
        raise

def adjust_opacity(image, opacity):
    """Ajusta a opacidade da imagem"""
    if opacity >= 1:
        return image
    
    # Criar uma nova imagem com alpha ajustado
    alpha = image.split()[3]
    alpha = ImageEnhance.Brightness(alpha).enhance(opacity)
    image.putalpha(alpha)
    return image

def resize_proportional(image, target_size):
    """Redimensiona a imagem mantendo a proporção"""
    original_width, original_height = image.size
    ratio = min(target_size / original_width, target_size / original_height)
    new_width = int(original_width * ratio)
    new_height = int(original_height * ratio)
    return image.resize((new_width, new_height), Image.LANCZOS)

def create_tiled_pattern(base_image, watermark_tile):
    """Cria padrão repetido com a marca d'água rotacionada"""
    # Criar uma camada transparente do mesmo tamanho da imagem base
    watermark_layer = Image.new('RGBA', base_image.size, (0, 0, 0, 0))
    
    # Tamanho do tile rotacionado
    tile_width, tile_height = watermark_tile.size
    
    # Calcular espaçamento (sobreposição de 20% para efeito contínuo)
    spacing_x = int(tile_width * 0.8)
    spacing_y = int(tile_height * 0.8)
    
    # Calcular offset para centralizar o padrão
    offset_x = -tile_width // 2
    offset_y = -tile_height // 2
    
    # Preencher toda a imagem com o padrão repetido
    for y in range(offset_y, base_image.height + tile_height, spacing_y):
        for x in range(offset_x, base_image.width + tile_width, spacing_x):
            # Posicionar o tile
            pos_x = x
            pos_y = y
            
            # Colar o tile na camada de marca d'água
            if pos_x < base_image.width and pos_y < base_image.height:
                watermark_layer.paste(watermark_tile, (pos_x, pos_y), watermark_tile)
    
    # Combinar com a imagem base
    result = Image.alpha_composite(base_image, watermark_layer)
    return result

def apply_diagonal_watermark(image):
    """Aplica a marca d'água em padrão diagonal repetido por toda a imagem"""
    try:
        # Converter imagem principal para RGBA
        main_image = image.convert("RGBA")
        
        # Abrir logo (marca d'água)
        watermark = Image.open(LOGO_FILENAME).convert("RGBA")
        
        # Aplicar transparência à marca d'água
        watermark = adjust_opacity(watermark, WATERMARK_OPACITY)
        
        # Redimensionar a logo
        base_size = min(main_image.width, main_image.height)
        watermark_size = int(base_size * WATERMARK_SCALE)
        watermark = resize_proportional(watermark, watermark_size)
        
        # Rotacionar a logo
        rotated_watermark = watermark.rotate(ROTATION_ANGLE, expand=True, resample=Image.BICUBIC)
        
        # Criar padrão repetido
        watermarked = create_tiled_pattern(main_image, rotated_watermark)
        
        return watermarked
        
    except Exception as e:
        logger.error(f"Erro ao aplicar marca d'água diagonal: {e}")
        raise

@app.route('/watermark', methods=['GET'])
def watermark_image():
    """Endpoint para aplicar marca d'água"""
    try:
        # Verificar parâmetro de URL
        image_url = request.args.get('url')
        if not image_url:
            return {"error": "Parâmetro 'url' é obrigatório"}, 400
        
        # Verificar se a logo existe
        if not check_logo():
            return {"error": f"Logo '{LOGO_FILENAME}' não encontrada"}, 500
        
        logger.info(f"Processando imagem: {image_url}")
        
        # Baixar imagem
        original_image = download_image(image_url)
        
        # Aplicar marca d'água
        watermarked_image = apply_diagonal_watermark(original_image)
        
        # Converter para bytes
        img_io = BytesIO()
        
        # Determinar formato baseado na extensão da URL ou usar JPEG como padrão
        if image_url.lower().endswith(('.png', '.gif', '.bmp', '.tiff')):
            watermarked_image.save(img_io, 'PNG')
            img_io.seek(0)
            mimetype = 'image/png'
        else:
            watermarked_image = watermarked_image.convert('RGB')
            watermarked_image.save(img_io, 'JPEG', quality=95)
            img_io.seek(0)
            mimetype = 'image/jpeg'
        
        # Retornar imagem
        return send_file(
            img_io,
            mimetype=mimetype,
            as_attachment=False,
            download_name='watermarked_image.jpg' if mimetype == 'image/jpeg' else 'watermarked_image.png'
        )
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro de rede: {e}")
        return {"error": "Não foi possível baixar a imagem"}, 400
    except Exception as e:
        logger.error(f"Erro interno: {e}")
        return {"error": "Erro ao processar imagem"}, 500

@app.route('/health', methods=['GET'])
def health_check():
    """Endpoint de health check"""
    return {"status": "healthy", "logo_exists": os.path.exists(LOGO_FILENAME)}

if __name__ == '__main__':
    # Verificar se a logo existe antes de iniciar
    if not os.path.exists(LOGO_FILENAME):
        print(f"❌ AVISO: Arquivo '{LOGO_FILENAME}' não encontrado na pasta atual!")
        print("Por favor, coloque a logo na mesma pasta do script.")
    else:
        print("🤖 Servidor Flask iniciado com sucesso!")
        print(f"📁 Logo usada: {LOGO_FILENAME}")
        print(f"🎨 Opacidade: {WATERMARK_OPACITY * 100}%")
        print(f"📐 Rotação: {ROTATION_ANGLE} graus")
        print(f"🔍 Escala: {WATERMARK_SCALE * 100}%")
        print(f"🔄 Padrão: Repetido lado a lado")
        print(f"🌐 Endpoint: http://localhost:5000/watermark?url=URL_DA_IMAGEM")
    
    app.run(host='0.0.0.0', port=5000, debug=True)