import cv2
import boto3
import cProfile
import numpy as np
from ntpath import basename
from scipy import ndimage
from os import listdir
from pdf2image import convert_from_path
from getpass import getuser
from base64 import b64decode, b64encode
from pickle import load, dump, HIGHEST_PROTOCOL
from orion_functions import show_image
from extra_functions import draw_block_lines
from OrganizeTable import organice_table
from Totales import total_total
import logging
import json

# with open('../config.json') as json_file:
#     cfg = json.load(json_file)

# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger("ocr_log")
# logger.setLevel(logging.INFO)


# def rm_noise(img):

#     #filtered = cv2.adaptiveThreshold(img.astype(np.uint8), 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 7, 41)
#     filte = cv2.adaptiveThreshold(img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
#                                   cv2.THRESH_BINARY, 11, 2)
#     kernel = np.ones((2, 2), np.uint8)
#     #kernel1 = np.ones((4, 4), np.uint8)
#     kernel1 = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], np.uint8)
#     # kernel1=kernel
#     close = cv2.morphologyEx(filte, cv2.MORPH_CLOSE, kernel)
#     open_ = cv2.morphologyEx(close, cv2.MORPH_OPEN, kernel1)
#     image = cv2.erode(open_, kernel, iterations=2)

#     return image


class Block:
    '''
    Clase que contiene todos lod bloques tipo LINE que entrega 
    aws textract
    Entrada: Variable block tipo diccionario devuelta por aws
    Salida: Toda la informacion referente al bloque en objeto tipo Block 
    '''
    def __init__(self, block):
        super().__init__()
        self.text = block['Text']
        self.type = block['BlockType']
        self.id = block['Id']
        self.height = block['Geometry']['BoundingBox']['Height']
        self.top = block['Geometry']['BoundingBox']['Top']
        self.width = block['Geometry']['BoundingBox']['Width']
        self.left = block['Geometry']['BoundingBox']['Left']
        self.p0 = block['Geometry']['Polygon'][0]
        self.p1 = block['Geometry']['Polygon'][1]
        self.page = block['Page']
        self.confidence = block['Confidence']
        self.relationships = block['Relationships']
        self.grupo_tag = None
        self.tag = None

    def convert_coord_to_pixels(self, shapes):
        self.width = int(self.width * shapes[1])
        self.height = int(self.height * shapes[0])
        self.left = int(self.left * shapes[1])
        self.top = int(self.top * shapes[0])

        #self.p0['X'] = self.p0['X'] * shapes[1]
        #self.p1['X'] = self.p1['X'] * shapes[1]
        #self.p0['Y'] = self.p0['Y'] * shapes[0]
        #self.p1['Y'] = self.p1['Y'] * shapes[0]

    def get_scaling_block(self, shapes):
        x0 = self.p0['X']
        x1 = self.p1['X']
        y0 = self.p0['Y']
        y1 = self.p1['Y']
        scaling = (y1 - y0)/(x1 - x0) if (x1-x0) else 0

        return scaling


class Page:
    '''
    Clase para guardar y manipular la informacion por pagina del
    EF.
    Entrada: 
    -page_number
    -page_image
    -response
    -from_backup
    Salida: Toda la informacion de la pagina en los atributos del objeto Page.
    '''
    def __init__(self, page_number, page_image, response, from_backup=False):
        super().__init__()
        self.max_width = 2000
        self.page_number = page_number
        self.page_image = page_image
        if from_backup:
            self.aws_response = response
        else:
            self.amazon_service()
            self.make_rotation_angle()

        self.make_block_lines()
        self.make_rescale()

    def amazon_service(self):
        """
        Agrupa la parte alfabetica con parte numerica en los EEFF.
        Entrada: Paths de la imagen.
        Salida: Diccionario con la la respuesta de lectura de amazon.
        """
        base64_image = cv2.imencode('.PNG', self.page_image)[1].tostring()
        client = boto3.client('textract')
        response = client.analyze_document(
            Document={'Bytes': base64_image}, FeatureTypes=["TABLES"])

        self.aws_response = response["Blocks"]

    def make_block_lines(self):
        block_lines = []
        for block in self.aws_response:
            if block['BlockType'] == 'LINE':
                block['Page'] = self.page_number
                block_lines.append(Block(block))

        self.block_lines = block_lines

    def make_rotation_angle(self):
        page_blocks = []
        for block in self.aws_response:
            if block['BlockType'] == 'LINE':
                pt1 = block['Geometry']['Polygon'][0]
                pt1 = (pt1['X'] * self.page_image.shape[1],
                       pt1['Y']*self.page_image.shape[0])
                pt2 = block['Geometry']['Polygon'][1]
                pt2 = (pt2['X']*self.page_image.shape[1],
                       pt2['Y']*self.page_image.shape[0])
                page_blocks.append([pt1, pt2])

        slopes = [(y2 - y1)/(x2 - x1) if (x2-x1)
                  else 0 for (x1, y1), (x2, y2) in page_blocks]

        rad_angles = [np.arctan(x) for x in slopes]
        # Convirtiendo de radianes a grados
        deg_angles = [np.degrees(x) for x in rad_angles]
        # Histograma de los todos los angulos en grados.
        histo = np.histogram(deg_angles, bins=180)
        # Tomando el angulo mas comun.
        rotation_number = histo[1][np.argmax(histo[0])]
        if rotation_number > 45:
            rotation_number = -(90-rotation_number)
        elif rotation_number < -45:
            rotation_number = 90 - abs(rotation_number)
        if abs(rotation_number) > 0.8:
            # Retornando imagen rotada
            angle = rotation_number
            #roted_image = ndimage.rotate(pages[num_page], rotation_number)
            # show_image(roted_image)
        else:
            angle = rotation_number
            # show_image(pages[num_page])

        if angle != 0:
            self.page_image = ndimage.rotate(self.page_image, angle)
            self.amazon_service()

    def scale_page(self):
        dimension = (self.max_width, int(
            self.page_image.shape[0]/self.page_image.shape[1] * self.max_width))
        page = cv2.resize(
            self.page_image, dimension, interpolation=cv2.INTER_AREA)
        self.page_image = page

    def make_rescale(self):
        self.scale_page()
        shape = self.page_image.shape
        # Coordenadas a pixeles.
        for i, block in enumerate(self.block_lines):
            self.block_lines[i].convert_coord_to_pixels(shape)


class Document:
    '''
    Clase contenedora de toda la informacion extraible del documento
    organizada por paginas.
    Entrada: Path del documento
    Salida: Objeto con toda la informacion extraible del EF.
    '''
    def __init__(self, path):
        super().__init__()
        self.path = path
        self.groups = None
        self.file_name = basename(self.path)
        self.pages_list = []
        self.get_aws_response()

    def save_backup(self, response):
        logger.info("Saving buckup.")
        base64_pages = []
        for page in self.pages_list:
            #page = page.page_image
            page_encode = b64encode(
                cv2.imencode('.jpg', page.page_image)[1]).decode()
            base64_pages.append(page_encode)

        backup = {}
        backup['pages'] = base64_pages
        backup['response'] = response
        if getuser() == 'pdi' or getuser() == 'orion':
            with open(cfg['backups']+self.file_name+'.p', 'wb') as fp:
                dump(backup, fp, protocol=HIGHEST_PROTOCOL)

    def load_backup(self):
        logger.info("Loading from buckup.")
        if False:
            with open(cfg['backups']+self.file_name+'.p', 'rb') as fp:
                backup = load(fp)
                response = backup['response']

            pages = []
            for i, page in enumerate(backup['pages']):
                str_decode = b64decode(page)
                mat_decode = np.frombuffer(str_decode, dtype=np.uint8)
                img_decode = cv2.imdecode(mat_decode, flags=1)
                gray_page = cv2.cvtColor(img_decode, cv2.COLOR_BGR2GRAY)

                if gray_page.shape[0] > 2000 and '.tif' in self.path:
                    gray_page = rm_noise(gray_page)
                else:
                    gray_page = cv2.medianBlur(gray_page, 1)

                self.pages_list.append(
                    Page(i, gray_page, response[i], from_backup=True))

            return True
        else:
            return False

    def get_aws_response(self):        
        # Dividir documento en paginas
        # Preguntar por backup de archivo
        backup = self.load_backup()

        if not(backup):
            logger.info("Getting aws response.")
            if self.path.endswith('.pdf'):
                images = convert_from_path(self.path)
                image_pages = []
                for pil_image in images:
                    page = np.array(pil_image)
                    page = page[:, :, ::-1].copy()
                    page = cv2.cvtColor(page, cv2.COLOR_BGR2GRAY)
                    image_pages.append(page)

            elif self.path.endswith(('.tiff', '.tif')):
                
                pages = cv2.imreadmulti(self.path)
                print(pages)
                image_pages = pages[1]

            else:
                logger.warning("The file does not have the correct extension.")
            
            responses = []
            for i, page in enumerate(image_pages):
                # Creacion de cada pagina con la clase Page
                new_page = Page(i, page, None, from_backup=False)
                self.pages_list.append(new_page)
                responses.append(new_page.aws_response)
                
                
            ## BACKUP RESPUESTA AMAZON ##
            self.save_backup(responses)
            ## -- ##

    def get_all_block_lines(self):
        return sum([page.block_lines for page in self.pages_list], [])


if __name__ == "__main__":
    file_path = '/home/orion/Descargas/900327563EEFFIFRS.tif'
    EFDocument = Document(file_path)
    print()

