import traceback
import StringIO
import psycopg2
import matplotlib
matplotlib.use('Agg')
# import error forces us to import cbook here; see 
# https://groups.google.com/forum/?fromgroups=#!topic/modwsgi/97bnQk9ojtY
import matplotlib.cbook
import matplotlib.backends.backend_agg

# in pixels, floating point for calculations
image_width = 600.0
image_height = 400.0

# in pixels
bottom_whitespace = 60
min_max_text_y = 40
val_text_y = 20

uncaught_exception_data = """An error occurred while generating this plot.  Please report this incident 
to xnat-admin@incf.org.
"""

class WSGIError(Exception):
    """base class for WSGI script errors"""

class ClientError(WSGIError):

    def __init__(self, message):
        WSGIError.__init__(self)
        self.status = '400 Bad Request'
        self.message = message
        return

def application(environ, start_response):
    try:
        data = generate_png(environ)
        status = '200 OK'
        content_type = 'image/png'
    except WSGIError, exc:
        data = '%s\n' % exc.message
        status = exc.status
        content_type = 'text/plain'
    except:
        environ['wsgi.errors'].write(traceback.format_exc())
        status = '500 Internal Server Error'
        data = uncaught_exception_data
        content_type = 'text/plain'
    response_headers = [('Content-type', content_type),
                        ('Content-Length', str(len(data)))]
    start_response(status, response_headers)
    return [data]

def generate_png(environ):
    db_password = open('/home/ch/.xnat_db_pw').read().rstrip('\n')
    uri_parts = environ['REQUEST_URI'].split('/')
    try:
        (empty, parts, parameter, value) = uri_parts
        value = float(value)
        query = "SELECT snr FROM incf_basicstructuralqadata"
    except ValueError:
        # unpack tuple of wrong size or bad float
        raise ClientError('malformed request URL')
    if parameter == 'snr':
        pass
    else:
        raise ClientError('unknown plot type "%s"' % parameter)
    db = psycopg2.connect(host='localhost', 
                          user='xnat', 
                          database='xnat', 
                          password=db_password)
    try:
        c = db.cursor()
        c.execute(query)
        vals = [ row[0] for row in c ]
        c.close()
    finally:
        db.close()
    vals.sort()
    min_val = min(vals)
    max_val = max(vals)
    i = 0
    while i < len(vals):
        if value < vals[i]:
            break
        i += 1
    pct = float(i)/len(vals)

    # trim top and bottom
    n_bottom = int(0.01 * len(vals))
    n_top = int(0.01 * len(vals))
    plot_vals = vals[n_bottom:-n_top]

    fig = matplotlib.figure.Figure()
    fig.set_facecolor('w')
    fig.set_size_inches(image_width / fig.get_dpi(), 
                        image_height / fig.get_dpi())
    fig.suptitle('SNR')
    bottom_f = bottom_whitespace / image_height
    h_f = 1.0 - bottom_f - 0.2
    ax = fig.add_axes([0.1, 0.1+bottom_f, 0.8, h_f], 
                      xlabel='SNR', 
                      ylabel='Count')
    min_max_text = 'min = %.1f, max = %.1f' % (min_val, max_val)
    min_max_text_y_f = min_max_text_y / image_height
    fig.text(0.5, 
             min_max_text_y_f, 
             min_max_text, 
             horizontalalignment='center', 
             verticalalignment='center')
    val_text = 'value = %.1f, percentile = %d' % (value, int(100*pct))
    val_text_y_f = val_text_y / image_height
    fig.text(0.5, 
             val_text_y_f, 
             val_text, 
             horizontalalignment='center', 
             verticalalignment='center')
    ax.hist(plot_vals, bins=100)
    ax.axvline(value, color='k')
    canvas = matplotlib.backends.backend_agg.FigureCanvasAgg(fig)
    so = StringIO.StringIO()
    canvas.print_png(so)
    data = so.getvalue()
    so.close()

    return data

# eof
