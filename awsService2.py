import cv2
import json
import boto3
import numpy as np
from scipy import ndimage
from pdf2image import convert_from_path
import base64
import multiprocessing
#import time
#from base64 import b64decode, b64encode
from fuzzywuzzy import fuzz
import sys


keysProofOfPayment=[
    # "bancolombia",
    "compania","nit compania","fecha actual",
    "numero de cuenta","tipo de cuenta","entidad",
    "cuenta local","nombre de beneficiario",
    "documento","valor","cheque",
    "concepto","referencia","estado",
    "fecha de aplicacion"
]


def aux_amazon_service(pil_image):
    page = np.array(pil_image)
    page = page[:, :, ::-1].copy()
    page = cv2.cvtColor(page, cv2.COLOR_BGR2BGRA)
    base64_image = cv2.imencode('.PNG',page)[1].tostring()
    client = boto3.client('textract')
    response = client.analyze_document(Document={'Bytes': base64_image}, FeatureTypes=["TABLES"])

    return response,page

def amazon_service(path):
    """
    Utiliza el servicio de Amazon Textrac.
    Entrada: Paths de la imagen.
    Salida: Diccionario con la la respuesta de lectura de amazon.
    """

    if path.endswith('.pdf'):
        images = convert_from_path(path, last_page=30)
        #
        pool = multiprocessing.Pool()
        documentResponse = pool.map(aux_amazon_service, images)
        pool.close()
        pool.join()
        responseList=list(map(lambda x: x[0],documentResponse))
        pages=list(map(lambda x: x[1],documentResponse))
    return responseList,pages


def filter_table(list_response):
    """
    Filtra Tablas
    """
    responseFilter=[]
    for page in list_response:
        responseFilter.append(list(filter(lambda x: x['BlockType']=='TABLE',page['Blocks'])))

    return responseFilter

def filter_statement(responseDocument):
    """
    Filtra los datos de la respuesta que cumplen con la caracteristica de contener el 
    texto: "Recibo individual de pagos - Sucursal Virtual Empresas" ya que este texto es
    el titulo de cada tabla y por ello es un delimintante entre tabla y tabla.

    Tambien filtra aquellas lineas que contienen el texto : "Pago enviado por IMERCO S A"
    que se utiliza como delimitante final de la tabla(comprobante)
    """
    statementInicio = "Recibo individual de pagos - Sucursal Virtual Empresas"
    statementFinal = "Pago enviado por IMERCO S A"

    listStatementFilter=[]
    for page in responseDocument:
        linesFilter = list(filter(lambda x: x['BlockType']=='LINE',page['Blocks']))
        statementFilter = list(filter(lambda y: fuzz.ratio(statementInicio,y['Text'])>80 or fuzz.ratio(statementFinal,y['Text'])>80 ,linesFilter))
        listStatementFilter.append(statementFilter)

    return listStatementFilter


def cut_tables(listTables,images,limits):
    """
    Recortar las tablas que encuentra en cada pagina.
    Retorna un diccionario con las imagenes recortadas y sus correspondientes coordenadas en la pagina.

    """
    # shape = images[0].shape
    # normStandar = 1700
    # normStandar2 = 2200
    normStandar = images[0].shape
    edge = int((normStandar[0]/100)*1)
    # Se multiplica por 10000 inicialmente ya que se considera el tamaño estandar de 2200 por 1700
    # Para recortar la tabla se almacena los pixeles de la imagen que se ubiquen entre las
    # coordenadas dadas para la tabla.
    listImageAndCoorTable=[]
    for indexPage, pageTables in enumerate(listTables):
        # imgTable=[]
        for indexTable,table in enumerate(pageTables):
            dictionaryImgCoor={}
            dictionaryCoor={}
            coorXStartTable = int(table['Geometry']['BoundingBox']['Left']*normStandar[1]) - edge
            coorXEndTable = coorXStartTable + int(table['Geometry']['BoundingBox']['Width']*normStandar[1]) + edge + edge
            if indexTable == 0:
                coorYStartTable = int(limits[indexPage][0]['Geometry']['BoundingBox']['Top']*normStandar[0])-edge
                coorYEndTable = int(limits[indexPage][1]['Geometry']['BoundingBox']['Top']*normStandar[0])+int(limits[indexPage][1]['Geometry']['BoundingBox']['Height']*normStandar[0])+edge
            elif indexTable ==1:
                coorYStartTable = int(limits[indexPage][2]['Geometry']['BoundingBox']['Top']*normStandar[0])-edge
                coorYEndTable = int(limits[indexPage][3]['Geometry']['BoundingBox']['Top']*normStandar[0])+int(limits[indexPage][3]['Geometry']['BoundingBox']['Height']*normStandar[0])+edge
            else:
                coorYStartTable = int(limits[indexPage][4]['Geometry']['BoundingBox']['Top']*normStandar[0])-edge
                coorYEndTable = int(limits[indexPage][5]['Geometry']['BoundingBox']['Top']*normStandar[0])+int(limits[indexPage][5]['Geometry']['BoundingBox']['Height']*normStandar[0])+edge

            # coorTable almacena las coordenadas de los cuatro vertices de la tabla.
            # widthTable = int(coorTable['Width']*normStandar[1])
            # heightTable = int(coorTable['Height']*normStandar[0])
            # leftTable = int(coorTable['Left']*normStandar[1])
            # topTable = int(coorTable['Top']*normStandar[0])
            #imgTable = images[indexPage][topTable:topTable+heightTable, leftTable:leftTable+widthTable]
            dictionaryImgCoor['img']= images[indexPage][coorYStartTable: coorYEndTable,coorXStartTable:coorXEndTable]
            dictionaryCoor['xs']=coorXStartTable/normStandar[1]
            dictionaryCoor['xe']=coorXEndTable/normStandar[1]
            dictionaryCoor['ys']=coorYStartTable/normStandar[0]
            dictionaryCoor['ye']=coorYEndTable/normStandar[0]
            dictionaryCoor['width_img'] = normStandar[1] 
            dictionaryCoor['height_img'] = normStandar[0]
            dictionaryImgCoor['coor_table']=dictionaryCoor
            dictionaryImgCoor['page'] = indexPage
            listImageAndCoorTable.append(dictionaryImgCoor)

            # imgTable= images[indexPage][coorYStartTable: coorYEndTable,coorXStartTable:coorXEndTable]
            # #images['coorY inicial':'coorY final','coorX inicial':'coorX final']
            # cv2.imshow("imagen Recortada",imgTable)
            # cv2.waitKey(0)
            # cv2.destroyAllWindows()
                 

    return listImageAndCoorTable

def filter_lines_by_img_cut(response,listImageAndCoorTable):
    """
    Busca en response todas aquellas lineas cuyas coordenadas esten entre los limites dados
    por las coordenadas de cada tabla y las agrega al diccionario.
    """

    listImgAndLines=[]
    # Recorrer listImageAnd--
    for tableDescribe in listImageAndCoorTable:
        dictionaryImgLines={}
        # filtrar todas las lineas de la pagina donde se encuntra la pagina
        linesPageFilter = list(filter(lambda x: x['BlockType']=='LINE',response[tableDescribe['page']]['Blocks']))
        
        # filtrar todas aquellas que se encuentren dentro del recuadro dado por las coordenadas de la tabla.
        linesTableFilter = list(filter(lambda x:
        x['Geometry']['BoundingBox']['Left'] > tableDescribe['coor_table']['xs'] and
        x['Geometry']['BoundingBox']['Left'] + x['Geometry']['BoundingBox']['Width'] < tableDescribe['coor_table']['xe'] and
        x['Geometry']['BoundingBox']['Top'] > tableDescribe['coor_table']['ys'] and
        x['Geometry']['BoundingBox']['Top'] + x['Geometry']['BoundingBox']['Height'] < tableDescribe['coor_table']['ye'],
        linesPageFilter))

        dictionaryImgLines['img']=tableDescribe['img']
        dictionaryImgLines['lines']=linesTableFilter
        dictionaryImgLines['page']=tableDescribe['page']
        listImgAndLines.append(dictionaryImgLines)

    return listImgAndLines

def aux_aux_organize_info(text):
    """
    comparar si text esta en alguna de las claves(keys) del comprobante
    retorna true o false
    """
    for keyPayment in keysProofOfPayment:
        if fuzz.ratio(text,keyPayment)>90:
            return True
    return False

def image_to_base64(image_to_convert):
    # Codificando renglon en base 64
    retval, buffer = cv2.imencode('.png', image_to_convert)
    return "data:image/png;base64," + str(base64.b64encode(buffer))[2:].replace("'", "")
    # imgbin = (cv2.imencode('.png',image_to_convert)[1].tostring())
    # imgbin = imgbin.replace("b'","")
    # return imgbin.replace("'","")
    


def aux_organize_info(tableInfo):
    """
    funcion auxiliar de la funcion organiza_info_lines_key_value
    se realiza la parte de comparaion entre keys del comprobante y 
    entre el texto de cada linea de la tabla
    """
    dictionaryDataOrganize={}
    for keyPayment in keysProofOfPayment:
        for indexLine,line in enumerate(tableInfo['lines']):
            try:
                if fuzz.partial_ratio(line['Text'].lower(),keyPayment)>95:
                    if not(aux_aux_organize_info(tableInfo['lines'][indexLine + 1]['Text'].lower())):
                        if keyPayment=="documento":
                            dictionaryDataOrganize[keyPayment]=int(tableInfo['lines'][indexLine + 1]['Text'])
                            break
                        
                        elif keyPayment=="valor":
                            numStr=tableInfo['lines'][indexLine + 1]['Text']
                            dictionaryDataOrganize[keyPayment]=numStr.split(",")[0]
                            break

                        else:
                            dictionaryDataOrganize[keyPayment]=tableInfo['lines'][indexLine + 1]['Text']
                            break                
            except:
                print("error en funcion organize_info_lines_key_value")
                pass
    
    dictionaryDataOrganize['img']= image_to_base64(tableInfo['img'])
    dictionaryDataOrganize['page']=tableInfo['page']

    return dictionaryDataOrganize

def organize_info_lines_key_value(listLinesAndImg):
    """
    Organiza la informacion dada en las lineas de cada tabla en 
    un diccionario clave-valor para generara un archivo Json en donde cada item
    es de facil manejo para el envio de la informacion al cliente respectivo
    """
    listTableInfoOrganize=[]
    for tableInfo in listLinesAndImg:
        listTableInfoOrganize.append(aux_organize_info(tableInfo))
    #listTableInfoOrganize = list(map(lambda x:aux_organize_info(x),listLinesAndImg))
    
    return listTableInfoOrganize

def draw_img_and_print_data(listTableInfoOrganize):
    """
    mustra cada imagen e imprime la informacion del cliente en consola.
    """
    for table in listTableInfoOrganize:
        for key in keysProofOfPayment:
            try:
                print(key + ":" + table[key])
            except:
                print(key + ":" + "vacio")
                pass
        print("-------------------------------------------------------")
        cv2.imshow("imagen Recortada",table['img'])
        cv2.waitKey(0)
        cv2.destroyAllWindows()


    return 

def filter_paymente_abonado(listTableInfoOrganize):
    paymenteAbonado=list(filter(lambda x: 'abonado' in (x['estado']).lower(),listTableInfoOrganize))
    paymenteNotAbonado=list(filter(lambda x: 'abonado' not in (x['estado']).lower(),listTableInfoOrganize))

    return paymenteAbonado,paymenteNotAbonado

def aws_tables(path):
    """
    Llama a las funciones encargadas de utilizar el servicio de amazon Textrac
    y de filtrar las tablas del resultado retornado por amazon
    """
    # responseTextracAwsList contines la respuesta de Textrac Amazon para cada pagina.
    # pagesImg almacena las imagenes del documento
    print("Cargando paginas en Amazon Textrac")
    responseTextracAwsList,pagesImg = amazon_service(path)
    # listTables contiene las caracteristicas de las tablas encontradas en cada pagina
    print("Filtrando Tablas")
    listTables = filter_table(responseTextracAwsList)
    # listStatement contiene las lineas que se utilizan para limitar la tabla Y inicial y Y final
    print("generando coordenadas limites de cada tabla")
    listStatement = filter_statement(responseTextracAwsList)
    # listImageAndCoorTable contiene cada comprobante(imagen recortada) y sus correspondientes coordenadas
    print("cortando imagen de cada comprobante.")
    listImageAndCoorTable=cut_tables(listTables,pagesImg, listStatement)

    print("filtrando texto perteneciente a cada tabla")
    listLinesAndImg=filter_lines_by_img_cut(responseTextracAwsList,listImageAndCoorTable)

    print("organizando texto e imagen de cada comprobante")
    listTableInfoOrganize=organize_info_lines_key_value(listLinesAndImg)

    # Mostrar imagen e imprimir datos.
    # draw_img_and_print_data(listTableInfoOrganize)

    # filtrar comprobantes con estado diferente a abonado.
    print("filtrando abonados y no abonados")
    paymenteAbonado,paymenteNoAbonado = filter_paymente_abonado(listTableInfoOrganize)
    # draw_img_and_print_data(paymenteAbonado)


    print("Entregando Json")
    jsonResponse={}
    jsonResponse['comprobantes']=paymenteAbonado
    print(sys.getsizeof(jsonResponse))
    return (jsonResponse)



if __name__ == "__main__":

    response=aws_tables("../FilesTemp/rechazoonline200911.pdf")
