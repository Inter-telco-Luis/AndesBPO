import psycopg2
import json

def connection_db():
    '''
    Coneccion con base de datos
    '''
    # conn = psycopg2.connect(user="orion",
    #                         password="12345",
    #                         host="ec2-35-172-38-7.compute-1.amazonaws.com",
    #                         port="5432",
    #                         database="ocr")
    conn = psycopg2.connect(user="intertelcoluisr",
                            password="Exito!2019",
                            host="localhost",
                            port="5432",
                            database="comprobantes")
    return conn

def fill_db_comprobantes(imgName):
    '''
    Llenar tabla de comprobantes
    '''

    with open('comprobantes.json', 'r') as f:
        comprobantesJson = json.load(f)

    #print(comprobantesJson)
    for indexJson,data in enumerate(comprobantesJson["json"]["comprobantes"]):
        if(data["img"]==imgName):
            break 
    
    name = str(comprobantesJson["json"]["comprobantes"][indexJson]["nombre de beneficiario"])
    documento = str(comprobantesJson["json"]["comprobantes"][indexJson]["documento"])
    valor = comprobantesJson["json"]["comprobantes"][indexJson]["valor"]
    page = str(comprobantesJson["json"]["comprobantes"][indexJson]["page"])

    try:
        conn = connection_db()
        cur = conn.cursor()
        query ="INSERT INTO comprobantes (pdfname,name,idcard,value,pagina,hour,date) VALUES ('pdfName','"+name+"','"+documento+"','"+valor+"','"+page+"',CURRENT_TIME,CURRENT_DATE)"
        # query = "INSERT INTO events (url,classname,text) VALUES ('" + segment + "');"

        print(query)
        cur.execute(query)

        cur.close()
        conn.commit()

    except (Exception, psycopg2.DatabaseError) as error:
        print(error)
    finally:
        if conn is not None:
            conn.close()

if __name__ == "__main__":
    fill_db_comprobantes("1144050140829-687274-91.png")
