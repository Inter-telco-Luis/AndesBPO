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

def fill_db_comprobantes(segment):
    '''
    Llenar tabla de comprobantes
    '''
    with open('comprobantes.json', 'r') as f:
        comprobantesJson = json.load(f)

    print(comprobantesJson)
    
    
    
    
    try:
        conn = connection_db()
        cur = conn.cursor()

        # query = "INSERT INTO events (url,classname,text) VALUES ('" + segment + "');"
        query = "INSERT INTO comprobantes (pdfname,name,idcard,value,pagina,hour) VALUES ('" + segment[0] + "','"+segment[1]+"','"+segment[2]+"','"+segment[3]+"','"+segment[4]+"','"+segment[5]+"')"
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
    pass