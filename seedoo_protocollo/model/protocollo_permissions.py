# -*- coding: utf-8 -*-
# This file is part of Seedoo.  The COPYRIGHT file at the top level of
# this module contains the full copyright notices and license terms.
import datetime
import logging
import time
import functools

from openerp import SUPERUSER_ID, api, _
from openerp.osv import fields, osv

_logger = logging.getLogger(__name__)


class protocollo_protocollo(osv.Model):
    _inherit = 'protocollo.protocollo'

    def _get_protocolli(self, cr, uid, ids):
        if isinstance(ids, (list, tuple)) and not len(ids):
            return []
        if isinstance(ids, (long, int)):
            ids = [ids]

        protocolli = self.browse(cr, uid, ids, {'skip_check': True})
        return protocolli

    def _check_stato_assegnatario_competenza(self, cr, uid, protocollo, stato, assegnatario_employee_id=None):
        domain = [
            ('protocollo_id', '=', protocollo.id),
            ('tipologia_assegnazione', '=', 'competenza'),
            ('tipologia_assegnatario', '=', 'employee'),
            ('state', '=', stato)
        ]
        if assegnatario_employee_id:
            domain.append(('assegnatario_employee_id.id', '=', assegnatario_employee_id))
        else:
            domain.append(('assegnatario_employee_id.user_id.id', '=', uid))
        assegnazione_obj = self.pool.get('protocollo.assegnazione')
        assegnazione_ids = assegnazione_obj.search(cr, uid, domain)
        if len(assegnazione_ids) > 0:
            return True
        return False

    def _check_stato_assegnatore_competenza(self, cr, uid, protocollo, stato, assegnatario_uid=None, smist_ut_uff=False):
        if not assegnatario_uid:
            assegnatario_uid = uid
        assegnazione_obj = self.pool.get('protocollo.assegnazione')
        assegnazione_ids = assegnazione_obj.search(cr, uid, [
            ('assegnatore_id.user_id.id', '=', assegnatario_uid),
            ('protocollo_id', '=', protocollo.id),
            ('tipologia_assegnazione', '=', 'competenza'),
            ('state', '=', stato),
            ('smist_ut_uff', '=', smist_ut_uff)
        ])
        if len(assegnazione_ids) > 0:
            return True
        return False

    def _check_stato_assegnatario_competenza_ufficio(self, cr, uid, protocollo, stato, assegnatario_employee_id=None):
        if assegnatario_employee_id:
            cr.execute('''
                SELECT DISTINCT(pa.protocollo_id)
                FROM protocollo_assegnazione pa, hr_employee he, resource_resource rr
                WHERE pa.protocollo_id = %s AND
                      pa.tipologia_assegnatario = 'department' AND 
                      pa.tipologia_assegnazione = 'competenza' AND
                      pa.state = %s AND
                      pa.assegnatario_department_id = he.department_id AND
                      he.id = %s
            ''', (str(protocollo.id), stato, str(assegnatario_employee_id)))
        else:
            cr.execute('''
                SELECT DISTINCT(pa.protocollo_id)
                FROM protocollo_assegnazione pa, hr_employee he, resource_resource rr
                WHERE pa.protocollo_id = %s AND
                      pa.tipologia_assegnatario = 'department' AND 
                      pa.tipologia_assegnazione = 'competenza' AND
                      pa.state = %s AND
                      pa.assegnatario_department_id = he.department_id AND
                      he.resource_id = rr.id AND
                      rr.user_id = %s
            ''', (str(protocollo.id), stato, str(uid)))
        assegnazione_ids = [res[0] for res in cr.fetchall()]
        if len(assegnazione_ids) > 0:
            return True
        return False

    def _check_stato_assegnatario_conoscenza(self, cr, uid, protocollo, stato, assegnatario_uid=None):
        if not assegnatario_uid:
            assegnatario_uid = uid
        assegnazione_obj = self.pool.get('protocollo.assegnazione')
        assegnazione_ids = assegnazione_obj.search(cr, uid, [
            ('assegnatario_employee_id.user_id.id', '=', assegnatario_uid),
            ('protocollo_id', '=', protocollo.id),
            ('tipologia_assegnazione', '=', 'conoscenza'),
            ('tipologia_assegnatario', '=', 'employee'),
            ('state', '=', stato)
        ])
        if len(assegnazione_ids) > 0:
            return True
        return False

    def _check_stato_assegnatario_conoscenza_ufficio(self, cr, uid, protocollo, stato, assegnatario_uid=None):
        if not assegnatario_uid:
            assegnatario_uid = uid
        cr.execute('''
                    SELECT DISTINCT(pa.protocollo_id)
                    FROM protocollo_assegnazione pa, hr_employee he, resource_resource rr
                    WHERE pa.protocollo_id = %s AND
                          pa.tipologia_assegnatario = 'department' AND 
                          pa.tipologia_assegnazione = 'conoscenza' AND
                          pa.state = %s AND
                          pa.assegnatario_department_id = he.department_id AND
                          he.resource_id = rr.id AND
                          rr.user_id = %s
                ''', (str(protocollo.id), stato, str(assegnatario_uid)))
        assegnazione_ids = [res[0] for res in cr.fetchall()]
        if len(assegnazione_ids) > 0:
            return True
        return False

    def get_protocollo_types_by_group(self, cr, uid, module, group_xml_start_id, group_xml_end_id, mapping={'ingresso': 'in', 'uscita': 'out'}):
        types = []
        for type_key in mapping.keys():
            group_xml_id = module + '.' + group_xml_start_id + type_key + group_xml_end_id
            check_gruppo = self.user_has_groups(cr, uid, group_xml_id)
            if check_gruppo:
                types.append(mapping[type_key])
        return types

    ####################################################################################################################
    # Visibilità dei protocolli
    ####################################################################################################################
    def get_protocollo_base_visibile_ids(self, cr, uid, current_user_id, archivio_ids, archivio_ids_str,
                                          employee_ids, employee_ids_str,
                                          employee_department_ids, employee_department_ids_str):
        protocollo_visible_ids = []

        start_time = time.time()
        # un utente deve poter vedere i protocolli in bozza (IN e OUT) creati da lui
        cr.execute('''
            SELECT DISTINCT(pp.id)
            FROM protocollo_protocollo pp
            WHERE pp.state = 'draft' AND 
                  pp.user_id = %s AND 
                  pp.archivio_id IN (''' + archivio_ids_str + ''')
        ''', (current_user_id,))
        protocollo_ids_drafts = [res[0] for res in cr.fetchall()]
        protocollo_visible_ids.extend(protocollo_ids_drafts)
        _logger.info("---Query draft %s seconds ---" % (time.time() - start_time))

        start_time = time.time()
        # un utente deve poter vedere i protocolli (IN e OUT) registrati da lui
        if employee_ids:
            cr.execute('''
                SELECT DISTINCT(pp.id)
                FROM protocollo_protocollo pp
                WHERE pp.registration_date IS NOT NULL AND
                      pp.registration_employee_id IN (''' + employee_ids_str + ''') AND
                      pp.archivio_id IN (''' + archivio_ids_str + ''')
            ''')
            protocollo_ids_created = [res[0] for res in cr.fetchall()]
            protocollo_visible_ids.extend(protocollo_ids_created)
        _logger.info("---Query created %s seconds ---" % (time.time() - start_time))

        start_time = time.time()
        # un utente deve poter vedere i protocolli registrati (IN e OUT) assegnati a lui o al suo ufficio,
        # purchè lui o un dipendente del suo ufficio non abbia rifiutato la presa in carico
        if employee_ids and employee_department_ids:
            cr.execute('''
                SELECT DISTINCT(pa.protocollo_id)
                FROM protocollo_assegnazione pa, protocollo_protocollo pp
                WHERE pp.registration_date IS NOT NULL AND
                      pa.protocollo_id = pp.id AND
                      (
                          (pa.tipologia_assegnatario = 'employee' AND pa.assegnatario_employee_id IN (''' + employee_ids_str + ''') AND pa.parent_id IS NULL) OR 
                          (pa.tipologia_assegnatario = 'department' AND pa.assegnatario_department_id  IN (''' + employee_department_ids_str + '''))
                      ) AND
                      (
                          pa.protocollo_id NOT IN (
                              SELECT DISTINCT(pa.protocollo_id)
                              FROM protocollo_assegnazione pa
                              WHERE pa.tipologia_assegnatario = 'employee' AND
                                    pa.assegnatario_employee_department_id IN (''' + employee_department_ids_str + ''') AND
                                    pa.state = 'rifiutato'
                          ) 
                          OR 
                          pa.protocollo_id IN (
                            SELECT DISTINCT(pa.protocollo_id)
                                FROM protocollo_assegnazione pa
                                WHERE pa.tipologia_assegnatario = 'employee' AND pa.assegnatario_employee_id IN (''' + employee_ids_str + ''') AND 
                                pa.tipologia_assegnazione = 'conoscenza'
                          )
                      )
                      AND
                      pp.archivio_id IN (''' + archivio_ids_str + ''')
            ''')
            protocollo_ids_assigned_not_refused = [res[0] for res in cr.fetchall()]
            protocollo_visible_ids.extend(protocollo_ids_assigned_not_refused)
        _logger.info("---Query assigned_not_refused %s seconds ---" % (time.time() - start_time))

        start_time = time.time()
        # un utente deve poter vedere i protocolli (IN e OUT) registrati di cui è autore della assegnazione per
        # competenza (assegnatore)
        if employee_ids:
            cr.execute('''
                SELECT DISTINCT(pa.protocollo_id)
                FROM protocollo_assegnazione pa, protocollo_protocollo pp
                WHERE pp.registration_date IS NOT NULL AND
                      pa.protocollo_id = pp.id AND
                      pa.assegnatore_id IN (''' + employee_ids_str + ''') AND 
                      pa.tipologia_assegnazione = 'competenza' AND 
                      pa.parent_id IS NULL AND
                      pp.archivio_id IN (''' + archivio_ids_str + ''')
            ''')
            protocollo_ids_assegnatore = [res[0] for res in cr.fetchall()]
            protocollo_visible_ids.extend(protocollo_ids_assegnatore)
        _logger.info("---Query assegnatore %s seconds ---" % (time.time() - start_time))

        return protocollo_visible_ids


    def get_protocollo_configuration_visibile_ids(self, cr, uid, current_user_id, archivio_ids, archivio_ids_str,
                                          employee_ids, employee_ids_str,
                                          employee_department_ids, employee_department_ids_str,
                                          employee_department_child_ids, employee_department_child_ids_str, aoo_ids):
        protocollo_visible_ids = []
        assegnazione_obj = self.pool.get('protocollo.assegnazione')

        start_time = time.time()
        # un utente deve poter vedere i protocolli (IN, OUT, INTERNAL) REGISTRATI dal suo UFFICIO di appartenenza
        types = self.get_protocollo_types_by_group(cr, current_user_id, 'seedoo_protocollo', 'group_vedi_protocolli_', '_registrati_ufficio')
        if types and employee_department_ids:
            cr.execute('''
                SELECT DISTINCT(pp.id)
                FROM protocollo_protocollo pp
                WHERE pp.registration_date IS NOT NULL AND
                      pp.registration_employee_department_id IN (''' + employee_department_ids_str + ''') AND
                      pp.reserved=FALSE AND
                      pp.type IN (''' + str(types).strip('[]') + ''') AND
                      pp.archivio_id IN (''' + archivio_ids_str + ''')
            ''')
            protocollo_ids_department = [res[0] for res in cr.fetchall()]
            protocollo_visible_ids.extend(protocollo_ids_department)
        _logger.info("---Query department  %s seconds ---" % (time.time() - start_time))

        start_time = time.time()
        # un utente deve poter vedere i protocolli (IN, OUT, INTERNAL) REGISTRATI da un UFFICIO FIGLIO del suo ufficio di appartenenza.
        types = self.get_protocollo_types_by_group(cr, current_user_id, 'seedoo_protocollo', 'group_vedi_protocolli_', '_registrati_ufficio_figlio')
        if types and employee_department_child_ids:
            cr.execute('''
                SELECT DISTINCT(pp.id)
                FROM protocollo_protocollo pp
                WHERE pp.registration_date IS NOT NULL AND
                      pp.registration_employee_department_id IN (''' + employee_department_child_ids_str + ''') AND
                      pp.reserved=FALSE AND
                      pp.type IN (''' + str(types).strip('[]') + ''') AND
                      pp.archivio_id IN (''' + archivio_ids_str + ''')
            ''')
            protocollo_ids_department_childs = [res[0] for res in cr.fetchall()]
            protocollo_visible_ids.extend(protocollo_ids_department_childs)
        _logger.info("---Query ids_department_childs  %s seconds ---" % (time.time() - start_time))

        start_time = time.time()
        # un utente deve poter vedere QUALUNQUE protocollo (IN, OUT, INTERNAL) in stato BOZZA appartenente alla sua AOO
        types = self.get_protocollo_types_by_group(cr, current_user_id, 'seedoo_protocollo', 'group_vedi_protocolli_', '_bozza')
        if types and aoo_ids:
            protocollo_ids_aoo = self.search(cr, uid, [
                ('type', 'in', types),
                ('state', '=', 'draft'),
                ('aoo_id', 'in', aoo_ids),
                ('archivio_id', 'in', archivio_ids)
            ])
            protocollo_visible_ids.extend(protocollo_ids_aoo)
        _logger.info("---Query aoo  %s seconds ---" % (time.time() - start_time))

        start_time = time.time()
        # un utente deve poter vedere QUALUNQUE protocollo (IN, OUT, INTERNAL) REGISTRATO da un utente della sua AOO
        types = self.get_protocollo_types_by_group(cr, current_user_id, 'seedoo_protocollo', 'group_vedi_protocolli_', '_registrati')
        if types and aoo_ids:
            protocollo_ids_aoo = self.search(cr, uid, [
                ('type', 'in', types),
                ('registration_date', '!=', False),
                ('aoo_id', 'in', aoo_ids),
                ('archivio_id', 'in', archivio_ids)
            ])
            protocollo_visible_ids.extend(protocollo_ids_aoo)
        _logger.info("---Query aoo 2  %s seconds ---" % (time.time() - start_time))

        start_time = time.time()
        # un utente deve poter vedere i protocolli (IN, OUT, INTERNAL) REGISTRATI e ASSEGNATI ad un UTENTE del suo UFFICIO di appartenenza
        types = self.get_protocollo_types_by_group(cr, current_user_id, 'seedoo_protocollo', 'group_vedi_protocolli_', '_registrati_ass_ut_uff')
        if types and employee_department_ids:
            assegnazione_ids = assegnazione_obj.search(cr, uid, [
                ('tipologia_assegnatario', '=', 'employee'),
                ('parent_id', '=', False),
                ('assegnatario_employee_department_id', 'in', employee_department_ids)
            ])
            protocollo_visible_ids.extend(self.search(cr, uid, [
                ('type', 'in', types),
                ('registration_date', '!=', False),
                ('assegnazione_ids', 'in', assegnazione_ids),
                ('reserved', '=', False),
                ('archivio_id', 'in', archivio_ids)
            ]))
        _logger.info("---Query registrati_ass_ut_uff  %s seconds ---" % (time.time() - start_time))

        start_time = time.time()
        # un utente deve poter vedere i protocolli (IN, OUT, INTERNAL) REGISTRATI e ASSEGNATI ad un suo UFFICIO FIGLIO
        types = self.get_protocollo_types_by_group(cr, current_user_id, 'seedoo_protocollo', 'group_vedi_protocolli_', '_registrati_ass_uff_fig')
        if types and employee_department_child_ids:
            assegnazione_ids = assegnazione_obj.search(cr, uid, [
                ('tipologia_assegnatario', '=', 'department'),
                # ('assegnatario_department_parent_id', '=', employee.department_id.id)
                ('assegnatario_department_id', 'in', employee_department_child_ids)
            ])
            protocollo_visible_ids.extend(self.search(cr, uid, [
                ('type', 'in', types),
                ('registration_date', '!=', False),
                ('assegnazione_ids', 'in', assegnazione_ids),
                ('reserved', '=', False),
                ('archivio_id', 'in', archivio_ids)
            ]))
        _logger.info("---Query ass_uff_fig  %s seconds ---" % (time.time() - start_time))

        start_time = time.time()
        # un utente deve poter vedere i protocolli (IN e OUT) REGISTRATI e ASSEGNATI ad un UTENTE di un suo UFFICIO FIGLIO
        types = self.get_protocollo_types_by_group(cr, current_user_id, 'seedoo_protocollo', 'group_vedi_protocolli_', '_registrati_ass_ut_uff_fig')
        if types and employee_department_child_ids:
            assegnazione_ids = assegnazione_obj.search(cr, uid, [
                ('tipologia_assegnatario', '=', 'employee'),
                ('parent_id', '=', False),
                # ('assegnatario_employee_department_id.parent_id.id', '=', employee.department_id.id)
                ('assegnatario_employee_department_id', 'in', employee_department_child_ids)
            ])
            protocollo_visible_ids.extend(self.search(cr, uid, [
                ('type', 'in', types),
                ('registration_date', '!=', False),
                ('assegnazione_ids', 'in', assegnazione_ids),
                ('reserved', '=', False),
                ('archivio_id', 'in', archivio_ids)
            ]))
        _logger.info("---Query ass_ut_uff_fig  %s seconds ---" % (time.time() - start_time))

        start_time = time.time()
        # un utente deve poter vedere i protocolli (IN, OUT, INTERNAL) REGISTRATI, ASSEGNATI e RIFIUTATI da un UTENTE del suo UFFICIO
        types = self.get_protocollo_types_by_group(cr, current_user_id, 'seedoo_protocollo', 'group_vedi_protocolli_', '_registrati_ass_rif_ut_uff')
        if types and employee_department_ids:
            assegnazione_ids = assegnazione_obj.search(cr, uid, [
                ('tipologia_assegnatario', '=', 'employee'),
                ('assegnatario_employee_department_id', 'in', employee_department_ids),
                ('state', '=', 'rifiutato')
            ])
            protocollo_visible_ids.extend(self.search(cr, uid, [
                ('type', 'in', types),
                ('registration_date', '!=', False),
                ('assegnazione_ids', 'in', assegnazione_ids),
                ('reserved', '=', False),
                ('archivio_id', 'in', archivio_ids)
            ]))
        _logger.info("---Query ass_rif_ut_uff  %s seconds ---" % (time.time() - start_time))

        return protocollo_visible_ids


    def _get_protocollo_visibile_ids(self, cr, uid, current_user_id, archivio_ids):
        protocollo_visible_ids = []

        employee_obj = self.pool.get('hr.employee')
        employee_ids = employee_obj.search(cr, uid, [('user_id', '=', current_user_id)])
        start_time = time.time()
        if len(employee_ids) > 0:

            employee_department_ids = []
            employee_department_child_ids = []
            aoo_ids = []
            for employee_id in employee_ids:
                employee = employee_obj.browse(cr, uid, employee_id)
                if employee.department_id:
                    employee_department = employee.department_id
                    employee_department_ids.append(employee_department.id)
                    for child in employee_department.all_child_ids:
                        employee_department_child_ids.append(child.id)
                    if employee_department.aoo_id:
                        aoo_ids.append(employee_department.aoo_id.id)

            employee_ids_str = ', '.join(map(str, employee_ids))
            employee_department_ids_str = ', '.join(map(str, employee_department_ids))
            employee_department_child_ids_str = ', '.join(map(str, employee_department_child_ids))
            archivio_ids_str = ', '.join(map(str, archivio_ids))

            ############################################################################################################
            # Visibilità dei protocolli: casi base
            ############################################################################################################
            protocollo_base_visible_ids = self.get_protocollo_base_visibile_ids(
                cr, uid, current_user_id, archivio_ids, archivio_ids_str, employee_ids, employee_ids_str,
                employee_department_ids, employee_department_ids_str)
            protocollo_visible_ids.extend(protocollo_base_visible_ids)
            ############################################################################################################

            ############################################################################################################
            # Visibilità dei protocolli: permessi in configurazione
            ############################################################################################################
            protocollo_configuration_visible_ids = self.get_protocollo_configuration_visibile_ids(
                cr, uid, current_user_id, archivio_ids, archivio_ids_str, employee_ids, employee_ids_str,
                employee_department_ids, employee_department_ids_str,
                employee_department_child_ids, employee_department_child_ids_str, aoo_ids)
            protocollo_visible_ids.extend(protocollo_configuration_visible_ids)
            ############################################################################################################

            protocollo_visible_ids = list(set(protocollo_visible_ids))

        _logger.info("--- %s start ---" % (start_time))
        _logger.info("--- %s len ---" % (len(protocollo_visible_ids)))

        return protocollo_visible_ids


    def _get_protocollo_archivio_ids(self, cr, archivio_ids):
        protocollo_archivio_ids = []

        ############################################################################################################
        # Visibilità dei protocolli archiviati
        ############################################################################################################
        archivio_ids_str = ', '.join(map(str, archivio_ids))
        start_time = time.time()
        # un utente deve poter vedere i protocolli in bozza (IN e OUT) creati da lui
        cr.execute('''
             SELECT DISTINCT(pp.id)
             FROM protocollo_protocollo pp
             WHERE pp.archivio_id IN (''' + archivio_ids_str + ''')
         ''')
        protocollo_ids_archivio = [res[0] for res in cr.fetchall()]
        _logger.info("---Query draft %s seconds ---" % (time.time() - start_time))

        # _logger.info("--- %s seconds ---" % (time.time() - start_time_total))
        _logger.info("--- %s start ---" % (start_time))
        _logger.info("--- %s len ---" % (len(protocollo_ids_archivio)))

        return protocollo_ids_archivio

    def _is_visible(self, cr, uid, ids, name, arg, context=None):
        return {}

    def _is_visible_search(self, cr, uid, obj, name, args, domain=None, context=None):
        protocollo_visible_ids = []
        protocollo_archivio_obj = self.pool.get('protocollo.archivio')
        is_current = True
        if context and context.has_key('uid') and context['uid']:
            current_user_id = context['uid']
            if 'is_current_archive' in context:
                is_current = context['is_current_archive']
            archivio_ids = protocollo_archivio_obj._get_archivio_ids(cr, current_user_id, is_current)
            if len(archivio_ids) > 0:
                check_gruppo_archive = self.user_has_groups(cr, current_user_id, 'seedoo_protocollo.group_vedi_protocolli_archiviati')
                if is_current or not check_gruppo_archive:
                    protocollo_visible_ids = self._get_protocollo_visibile_ids(cr, SUPERUSER_ID, current_user_id, archivio_ids)
                else:
                    protocollo_visible_ids = self._get_protocollo_archivio_ids(cr, archivio_ids)

        return [('id', 'in', protocollo_visible_ids)]

    def check_access_rule(self, cr, uid, ids, operation, context=None):
        if context and context.has_key('skip_check') and context['skip_check']:
            return ids
        return super(protocollo_protocollo, self).check_access_rule(cr, uid, ids, operation, context=context)

    def search_read(self, cr, uid, domain=None, fields=None, offset=0, limit=None, order=None, context=None):
        record_ids = self.search(cr, uid, domain or [], offset=offset, limit=limit, order=order, context=context)
        if not record_ids:
            return []

        if fields and fields == ['id']:
            # shortcut read if we only want the ids
            return [{'id': id} for id in record_ids]

        # read() ignores active_test, but it would forward it to any downstream search call
        # (e.g. for x2m or function fields), and this is not the desired behavior, the flag
        # was presumably only meant for the main search().
        # TODO: Move this to read() directly?
        read_ctx = dict(context or {})
        read_ctx.pop('active_test', None)
        read_ctx['skip_check'] = True

        result = self.read(cr, uid, record_ids, fields, context=read_ctx)
        if len(result) <= 1:
            return result

        # reorder read
        index = dict((r['id'], r) for r in result)
        return [index[x] for x in record_ids if x in index]

    def search(self, cr, uid, args, offset=0, limit=None, order=None, context=None, count=False):
        if context and context.has_key('skip_check') and context['skip_check']:
            return super(protocollo_protocollo, self).search(cr, SUPERUSER_ID, args, offset=offset, limit=limit, order=order, context=context, count=count)
        return super(protocollo_protocollo, self).search(cr, uid, args, offset=offset, limit=limit, order=order, context=context, count=count)

    def _apply_ir_rules(self, cr, uid, query, mode='read', context=None):
        if context and context.has_key('skip_check') and context['skip_check']:
            return
        return super(protocollo_protocollo, self)._apply_ir_rules(cr, uid, query, mode='read', context=context)

    def message_subscribe(self, cr, uid, ids, partner_ids, subtype_ids=None, context=None):
        if context and context.has_key('skip_check') and context['skip_check']:
            return True
        return super(protocollo_protocollo, self).message_subscribe(cr, uid, ids, partner_ids, subtype_ids=None, context=None)

    # def write(self, cr, uid, ids, vals, context=None):
    #     protocollo_ids = super(protocollo_protocollo, self).write(cr, uid, ids, vals, context=context)
    #     self.clear_cache()
    #     return protocollo_ids
    #
    # def create(self, cr, uid, vals, context=None):
    #     self.clear_cache()
    #     protocollo_id = super(protocollo_protocollo, self).create(cr, uid, vals, context=context)
    #     return protocollo_id
    #
    # def rifiuta_presa_in_carico(self, cr, uid, ids, context=None):
    #     result = super(protocollo_protocollo, self).rifiuta_presa_in_carico(cr, uid, ids, context=context)
    #     self.clear_cache()
    #     return result

    ####################################################################################################################

    ####################################################################################################################
    # Visibilità dei protocolli nella dashboard
    ####################################################################################################################

    def _non_classificati_visibility(self, cr, uid, ids, name, arg, context=None):
        return {}

    def _non_classificati_visibility_search(self, cr, uid, obj, name, args, domain=None, context=None):
        start = int(round(time.time() * 1000))

        cr.execute('''
            SELECT DISTINCT(pp.id) AS id
            FROM protocollo_protocollo pp, hr_employee he, resource_resource rr
            WHERE pp.classification IS NULL 
                AND pp.registration_employee_id = he.id
                AND he.resource_id = rr.id
                AND rr.user_id = %s
                AND pp.state IN ('registered', 'notified', 'waiting', 'sent', 'error')
                AND pp.is_imported = FALSE
        ''', (uid,))
        protocollo_visible_ids = [res[0] for res in cr.fetchall()]

        end = int(round(time.time() * 1000))
        _logger.info("_non_classificati_visibility_search: " + str(end - start))
        return [('id', 'in', protocollo_visible_ids)]

    def _non_classificati_visibility_count(self, cr, uid):
        time_start = datetime.datetime.now()
        archivio_ids = self.pool.get('protocollo.archivio').search(cr, uid, [('is_current', '=', True)])
        current_archivio_id = archivio_ids[0]

        sql_query = """SELECT COUNT(DISTINCT(pp.id)) AS id
            FROM protocollo_protocollo pp, hr_employee he, resource_resource rr
            WHERE pp.classification IS NULL 
                AND pp.archivio_id = %d
                AND pp.registration_employee_id = he.id
                AND he.resource_id = rr.id
                AND rr.user_id = %s
                AND pp.state IN ('registered', 'notified', 'waiting', 'sent', 'error')
                AND pp.is_imported = FALSE
        """ % (current_archivio_id, uid)

        cr.execute(sql_query)
        result = cr.fetchall()
        count_value = result[0][0]

        time_end = datetime.datetime.now()
        time_duration = time_end - time_start

        _logger.info("_non_classificati_visibility_count: %d - %.03f s" % (
            count_value,
            float(time_duration.microseconds) / 1000000
        ))

        return count_value

    def _non_fascicolati_visibility(self, cr, uid, ids, name, arg, context=None):
        return {}

    def _non_fascicolati_visibility_search(self, cr, uid, obj, name, args, domain=None, context=None):
        start = int(round(time.time() * 1000))

        cr.execute('''
            SELECT DISTINCT(p.id) FROM (
                SELECT DISTINCT(pa.protocollo_id) AS id
                FROM protocollo_protocollo pp, protocollo_assegnazione pa, hr_employee he, resource_resource rr
                WHERE pp.id = pa.protocollo_id
                    AND pa.assegnatario_employee_id = he.id
                    AND he.resource_id = rr.id
                    AND rr.user_id = %s
                    AND pp.registration_date IS NOT NULL
                    AND pa.tipologia_assegnatario = 'employee'
                    AND pa.tipologia_assegnazione = 'competenza'
                    AND pa.state = 'preso' 
                    AND pp.state IN ('registered', 'notified', 'waiting', 'sent', 'error')
                    AND pp.id NOT IN (SELECT protocollo_id FROM dossier_protocollo_rel)
                    
                UNION SELECT DISTINCT(pp.id) AS id
                    FROM protocollo_protocollo pp, hr_employee he, resource_resource rr
                    WHERE pp.registration_employee_id = he.id
                        AND he.resource_id = rr.id
                        AND rr.user_id = %s
                        AND pp.state IN ('registered', 'notified', 'waiting', 'sent', 'error')
                        AND pp.id NOT IN (SELECT protocollo_id FROM dossier_protocollo_rel))
                        p
        ''', (uid,uid))
        protocollo_visible_ids = [res[0] for res in cr.fetchall()]

        end = int(round(time.time() * 1000))
        _logger.info("_non_fascicolati_visibility_search: " + str(end - start))
        return [('id', 'in', protocollo_visible_ids)]

    def _non_fascicolati_visibility_count(self, cr, uid):
        time_start = datetime.datetime.now()
        archivio_ids = self.pool.get('protocollo.archivio').search(cr, uid, [('is_current', '=', True)])
        current_archivio_id = archivio_ids[0]

        sql_query = """SELECT COUNT ( DISTINCT(p.id)) FROM (
            SELECT DISTINCT(pa.protocollo_id) AS id
                FROM protocollo_protocollo pp, protocollo_assegnazione pa, hr_employee he, resource_resource rr
                WHERE pp.id = pa.protocollo_id
                    AND pp.archivio_id = %d
                    AND pa.assegnatario_employee_id = he.id
                    AND he.resource_id = rr.id
                    AND rr.user_id = %s
                    AND pp.registration_date IS NOT NULL
                    AND pa.tipologia_assegnatario = 'employee'
                    AND pa.tipologia_assegnazione = 'competenza'
                    AND pa.state = 'preso'
                    AND pp.state IN ('registered', 'notified', 'waiting', 'sent', 'error')
                    AND pp.id NOT IN (SELECT protocollo_id FROM dossier_protocollo_rel)
            
            UNION SELECT DISTINCT(pp.id) AS id
                FROM protocollo_protocollo pp, hr_employee he, resource_resource rr
                WHERE pp.archivio_id = %d
                    AND pp.registration_employee_id = he.id
                    AND he.resource_id = rr.id
                    AND rr.user_id = %s
                    AND pp.state IN ('registered', 'notified', 'waiting', 'sent', 'error')
                    AND pp.id NOT IN (SELECT protocollo_id FROM dossier_protocollo_rel))
                    p
        """ % (current_archivio_id, uid, current_archivio_id, uid,)

        cr.execute(sql_query)
        result = cr.fetchall()
        count_value = result[0][0]

        time_end = datetime.datetime.now()
        time_duration = time_end - time_start

        _logger.info("_non_fascicolati_visibility_count: %d - %.03f s" % (
            count_value,
            float(time_duration.microseconds) / 1000000
        ))

        return count_value

    def _bozza_creato_da_me_visibility(self, cr, uid, ids, name, arg, context=None):
        return {}

    def _bozza_creato_da_me_visibility_search(self, cr, uid, obj, name, args, domain=None, context=None):
        protocollo_visible_ids = self.search(cr, uid, [('state', '=', 'draft'), ('user_id', '=', uid)])
        return [('id', 'in', protocollo_visible_ids)]

    # @api.cr_uid
    # def _bozza_creato_da_me_visibility_count_in(self, cr, uid):
    #     return self._bozza_creato_da_me_visibility_count(cr, uid, "in")
    #
    # @api.cr_uid
    # def _bozza_creato_da_me_visibility_count_out(self, cr, uid):
    #     return self._bozza_creato_da_me_visibility_count(cr, uid, "out")

    @api.cr_uid
    def _bozza_creato_da_me_visibility_count_total(self, cr, uid):
        return self._bozza_creato_da_me_visibility_count(cr, uid, "")

    def _bozza_creato_da_me_visibility_count(self, cr, uid, protocollo_type):
        # if not protocollo_type:
        #     return 0

        time_start = datetime.datetime.now()

        sql_query = """SELECT COUNT(pp.id)
                       FROM protocollo_protocollo pp
                       WHERE pp.state = 'draft'
                            AND pp.user_id = %d""" % (uid)

        cr.execute(sql_query)
        result = cr.fetchall()
        count_value = result[0][0]

        time_end = datetime.datetime.now()
        time_duration = time_end - time_start

        _logger.info("_bozza_creato_da_me_visibility_count: %d - %.03f s" % (
            count_value,
            float(time_duration.microseconds) / 1000000
        ))

        return count_value

    def _assegnato_a_me_visibility(self, cr, uid, ids, name, arg, context=None):
        return {}

    def _assegnato_a_me_visibility_search(self, cr, uid, obj, name, args, domain=None, context=None):
        start = int(round(time.time() * 1000))

        cr.execute('''
            SELECT DISTINCT(pa.protocollo_id) 
            FROM protocollo_protocollo pp, protocollo_assegnazione pa, hr_employee he, resource_resource rr
            WHERE pp.id = pa.protocollo_id AND 
                  pa.assegnatario_employee_id = he.id AND
                  he.resource_id = rr.id AND
                  rr.user_id = %s AND
                  pp.registration_date IS NOT NULL AND
                  pa.tipologia_assegnatario = 'employee' AND 
                  pa.tipologia_assegnazione = 'competenza' AND
                  pa.state = 'assegnato' AND
                  pa.parent_id IS NULL AND
                  pp.state IN ('registered', 'notified', 'waiting', 'sent', 'error')
        ''', (uid,))
        protocollo_visible_ids = [res[0] for res in cr.fetchall()]
        end = int(round(time.time() * 1000))
        _logger.info("_assegnato_a_me_visibility_search: " + str(end - start))
        return [('id', 'in', protocollo_visible_ids)]

    # @api.cr_uid
    # def _assegnato_a_me_visibility_count_in(self, cr, uid):
    #     return self._assegnato_a_me_visibility_count(cr, uid, "in")
    #
    # @api.cr_uid
    # def _assegnato_a_me_visibility_count_out(self, cr, uid):
    #     return self._assegnato_a_me_visibility_count(cr, uid, "out")

    @api.cr_uid
    def _assegnato_a_me_visibility_count_total(self, cr, uid):
        return self._assegnato_a_me_visibility_count(cr, uid, "")

    def _assegnato_a_me_visibility_count(self, cr, uid, protocollo_type):
        # if not protocollo_type:
        #     return 0

        time_start = datetime.datetime.now()
        archivio_ids = self.pool.get('protocollo.archivio').search(cr, uid, [('is_current', '=', True)])
        current_archivio_id = archivio_ids[0]

        sql_query = """SELECT COUNT(DISTINCT(pa.protocollo_id)) 
            FROM protocollo_protocollo pp, protocollo_assegnazione pa, hr_employee he, resource_resource rr
            WHERE pp.id = pa.protocollo_id 
                AND pp.archivio_id = %d 
                AND pa.assegnatario_employee_id = he.id
                AND he.resource_id = rr.id
                AND rr.user_id = %d
                AND pp.registration_date IS NOT NULL
                AND pa.tipologia_assegnatario = 'employee'
                AND pa.tipologia_assegnazione = 'competenza'
                AND pa.state = 'assegnato'
                AND pa.parent_id IS NULL
                AND pp.state IN ('registered', 'notified', 'waiting', 'sent', 'error')
        """ % (current_archivio_id, uid)

        cr.execute(sql_query)
        result = cr.fetchall()
        count_value = result[0][0]

        time_end = datetime.datetime.now()
        time_duration = time_end - time_start

        _logger.info("_assegnato_a_me_visibility_count: %d - %.03f s" % (
            count_value,
            float(time_duration.microseconds) / 1000000
        ))

        return count_value

    def _assegnato_cc_visibility(self, cr, uid, ids, name, arg, context=None):
        return {}

    def _assegnato_cc_visibility_search(self, cr, uid, obj, name, args, domain=None, context=None):
        start = int(round(time.time() * 1000))

        cr.execute('''
            SELECT DISTINCT(pa.protocollo_id)
            FROM protocollo_protocollo pp, protocollo_assegnazione pa, hr_employee he, resource_resource rr
            WHERE pp.id = pa.protocollo_id AND
                  (
                       (pa.parent_id IS NULL AND pa.assegnatario_employee_id = he.id AND he.resource_id = rr.id AND rr.user_id = ''' + str(uid) + ''') OR
                       (pa.parent_id IS NOT NULL AND pa.assegnatario_employee_department_id = he.department_id AND pa.assegnatario_employee_id = he.id AND he.resource_id = rr.id AND rr.user_id = ''' + str(uid) + ''')
                  ) AND
                  pp.registration_date IS NOT NULL AND
                  pa.tipologia_assegnatario = 'employee' AND
                  pa.tipologia_assegnazione = 'conoscenza' AND
                  pa.state = 'assegnato' AND
                  pp.state IN ('registered', 'notified', 'waiting', 'sent', 'error', 'acts')
        ''')

        protocollo_visible_ids = [res[0] for res in cr.fetchall()]
        end = int(round(time.time() * 1000))
        _logger.info("_assegnato_cc_visibility_search: " + str(end - start))
        return [('id', 'in', protocollo_visible_ids)]

    # @api.cr_uid
    # def _assegnato_cc_visibility_count_in(self, cr, uid):
    #     return self._assegnato_cc_visibility_count(cr, uid, "in")
    #
    # @api.cr_uid
    # def _assegnato_cc_visibility_count_out(self, cr, uid):
    #     return self._assegnato_cc_visibility_count(cr, uid, "out")

    @api.cr_uid
    def _assegnato_cc_visibility_count_total(self, cr, uid):
        return self._assegnato_cc_visibility_count(cr, uid, "")

    def _assegnato_cc_visibility_count(self, cr, uid, protocollo_type):
        # if not protocollo_type:
        #     return 0

        time_start = datetime.datetime.now()
        archivio_ids = self.pool.get('protocollo.archivio').search(cr, uid, [('is_current', '=', True)])
        current_archivio_id = archivio_ids[0]

        sql_query = """
            SELECT COUNT(DISTINCT(pa.protocollo_id)) 
            FROM protocollo_protocollo pp, protocollo_assegnazione pa, hr_employee he, resource_resource rr
            WHERE pp.archivio_id = %d AND 
                  pp.id = pa.protocollo_id AND
                  (
                       (pa.parent_id IS NULL AND pa.assegnatario_employee_id = he.id AND he.resource_id = rr.id AND rr.user_id = %s) OR
                       (pa.parent_id IS NOT NULL AND pa.assegnatario_employee_department_id = he.department_id AND pa.assegnatario_employee_id = he.id AND he.resource_id = rr.id AND rr.user_id = %s)
                  ) AND
                  pp.registration_date IS NOT NULL AND
                  pa.tipologia_assegnatario = 'employee' AND 
                  pa.tipologia_assegnazione = 'conoscenza' AND 
                  pa.state = 'assegnato' AND
                  pp.state IN ('registered', 'notified', 'waiting', 'sent', 'error', 'acts')
        """ % (current_archivio_id, uid, uid)

        cr.execute(sql_query)
        result = cr.fetchall()
        count_value = result[0][0]

        time_end = datetime.datetime.now()
        time_duration = time_end - time_start

        _logger.info("_assegnato_cc_visibility_count: %d - %.03f s" % (
            count_value,
            float(time_duration.microseconds) / 1000000
        ))

        return count_value

    def _assegnato_a_me_cc_visibility(self, cr, uid, ids, name, arg, context=None):
        return {}

    def _assegnato_a_me_cc_visibility_search(self, cr, uid, obj, name, args, domain=None, context=None):
        start = int(round(time.time() * 1000))

        cr.execute('''
            SELECT DISTINCT(pa.protocollo_id) 
            FROM protocollo_protocollo pp, protocollo_assegnazione pa, hr_employee he, resource_resource rr
            WHERE pp.id = pa.protocollo_id AND 
                  pa.assegnatario_employee_id = he.id AND
                  he.resource_id = rr.id AND
                  rr.user_id = %s AND
                  pp.registration_date IS NOT NULL AND
                  pa.tipologia_assegnatario = 'employee' AND 
                  pa.tipologia_assegnazione = 'conoscenza' AND
                  pa.state = 'assegnato' AND
                  pa.parent_id IS NULL AND
                  pp.state IN ('registered', 'notified', 'waiting', 'sent', 'error')
        ''', (uid,))
        protocollo_visible_ids = [res[0] for res in cr.fetchall()]
        end = int(round(time.time() * 1000))
        _logger.info("_assegnato_a_me_cc_visibility_search: " + str(end - start))
        return [('id', 'in', protocollo_visible_ids)]

    # @api.cr_uid
    # def _assegnato_a_me_cc_visibility_count_in(self, cr, uid):
    #     return self._assegnato_a_me_cc_visibility_count(cr, uid, "in")
    #
    # @api.cr_uid
    # def _assegnato_a_me_cc_visibility_count_out(self, cr, uid):
    #     return self._assegnato_a_me_cc_visibility_count(cr, uid, "out")

    def _assegnato_a_me_cc_visibility_count(self, cr, uid, protocollo_type):
        if not protocollo_type:
            return 0

        time_start = datetime.datetime.now()
        archivio_ids = self.pool.get('protocollo.archivio').search(cr, uid, [('is_current', '=', True)])
        current_archivio_id = archivio_ids[0]

        sql_query = """SELECT COUNT(DISTINCT(pa.protocollo_id)) 
            FROM protocollo_protocollo pp, protocollo_assegnazione pa, hr_employee he, resource_resource rr
            WHERE pp.archivio_id = %d 
                AND pp.type = '%s'
                AND pp.id = pa.protocollo_id 
                AND pa.assegnatario_employee_id = he.id
                AND he.resource_id = rr.id
                AND rr.user_id = %d
                AND pp.registration_date IS NOT NULL
                AND pa.tipologia_assegnatario = 'employee' 
                AND pa.tipologia_assegnazione = 'conoscenza'
                AND pa.state = 'assegnato'
                AND pa.parent_id IS NULL
                AND pp.state IN ('registered', 'notified', 'waiting', 'sent', 'error')
        """ % (current_archivio_id, protocollo_type, uid)

        cr.execute(sql_query)
        result = cr.fetchall()
        count_value = result[0][0]

        time_end = datetime.datetime.now()
        time_duration = time_end - time_start

        _logger.info("_assegnato_a_me_cc_visibility_count: %d - %s - %.03f s" % (
            count_value,
            protocollo_type,
            float(time_duration.microseconds) / 1000000
        ))

        return count_value

    def _assegnato_a_mio_ufficio_visibility(self, cr, uid, ids, name, arg, context=None):
        return {}

    def _assegnato_a_mio_ufficio_visibility_search(self, cr, uid, obj, name, args, domain=None, context=None):
        start = int(round(time.time() * 1000))
        cr.execute('''
            SELECT DISTINCT(pa.protocollo_id) 
            FROM protocollo_protocollo pp, protocollo_assegnazione pa, hr_department hd, hr_employee he, resource_resource rr
            WHERE pp.id = pa.protocollo_id AND 
                  pa.assegnatario_department_id = hd.id AND
                  hd.id=he.department_id AND
                  he.resource_id = rr.id AND
                  rr.user_id = %s AND
                  pp.registration_date IS NOT NULL AND
                  pa.tipologia_assegnatario = 'department' AND 
                  pa.tipologia_assegnazione = 'competenza' AND
                  pa.state = 'assegnato' AND
                  pp.state IN ('registered', 'notified', 'waiting', 'sent', 'error')
        ''', (uid,))
        protocollo_visible_ids = [res[0] for res in cr.fetchall()]
        end = int(round(time.time() * 1000))
        _logger.info("_assegnato_a_mio_ufficio_visibility_search: " + str(end - start))
        return [('id', 'in', protocollo_visible_ids)]

    # @api.cr_uid
    # def _assegnato_a_mio_ufficio_visibility_count_in(self, cr, uid):
    #     return self._assegnato_a_mio_ufficio_visibility_count(cr, uid, "in")
    #
    # @api.cr_uid
    # def _assegnato_a_mio_ufficio_visibility_count_out(self, cr, uid):
    #     return self._assegnato_a_mio_ufficio_visibility_count(cr, uid, "out")

    @api.cr_uid
    def _assegnato_a_mio_ufficio_visibility_count_total(self, cr, uid):
        return self._assegnato_a_mio_ufficio_visibility_count(cr, uid, "")

    def _assegnato_a_mio_ufficio_visibility_count(self, cr, uid, protocollo_type):
        # if not protocollo_type:
        #     return 0

        time_start = datetime.datetime.now()
        archivio_ids = self.pool.get('protocollo.archivio').search(cr, uid, [('is_current', '=', True)])
        current_archivio_id = archivio_ids[0]

        sql_query = """SELECT COUNT(DISTINCT(pa.protocollo_id)) 
            FROM protocollo_protocollo pp, protocollo_assegnazione pa, hr_department hd, hr_employee he, resource_resource rr
            WHERE pp.archivio_id = %d 
                AND pp.id = pa.protocollo_id 
                AND pa.assegnatario_department_id = hd.id
                AND hd.id = he.department_id
                AND he.resource_id = rr.id
                AND rr.user_id = %d
                AND pp.registration_date IS NOT NULL
                AND pa.tipologia_assegnatario = 'department' 
                AND pa.tipologia_assegnazione = 'competenza'
                AND pa.state = 'assegnato'
                AND pp.state IN ('registered', 'notified', 'waiting', 'sent', 'error')
        """ % (current_archivio_id, uid)

        cr.execute(sql_query)
        result = cr.fetchall()
        count_value = result[0][0]

        time_end = datetime.datetime.now()
        time_duration = time_end - time_start

        _logger.info("_assegnato_a_mio_ufficio_visibility_count: %d - %.03f s" % (
            count_value,
            float(time_duration.microseconds) / 1000000
        ))

        return count_value

    def _assegnato_a_mio_ufficio_cc_visibility(self, cr, uid, ids, name, arg, context=None):
        return {}

    def _assegnato_a_mio_ufficio_cc_visibility_search(self, cr, uid, obj, name, args, domain=None, context=None):
        start = int(round(time.time() * 1000))
        cr.execute('''
            SELECT DISTINCT(pa.protocollo_id) 
            FROM protocollo_protocollo pp, protocollo_assegnazione pa, hr_department hd, hr_employee he, resource_resource rr
            WHERE pp.id = pa.protocollo_id AND 
                  pa.assegnatario_department_id = hd.id AND
                  hd.id=he.department_id AND
                  he.resource_id = rr.id AND
                  rr.user_id = %s AND
                  pp.registration_date IS NOT NULL AND
                  pa.tipologia_assegnatario = 'department' AND 
                  pa.tipologia_assegnazione = 'conoscenza' AND
                  pa.state = 'assegnato' AND
                  pp.state IN ('registered', 'notified', 'waiting', 'sent', 'error')
        ''', (uid,))
        protocollo_visible_ids = [res[0] for res in cr.fetchall()]
        end = int(round(time.time() * 1000))
        _logger.info("_assegnato_a_mio_ufficio_cc_visibility_search" + str(end - start))
        return [('id', 'in', protocollo_visible_ids)]

    # @api.cr_uid
    # def _assegnato_a_mio_ufficio_cc_visibility_count_in(self, cr, uid):
    #     return self._assegnato_a_mio_ufficio_cc_visibility_count(cr, uid, "in")
    #
    # @api.cr_uid
    # def _assegnato_a_mio_ufficio_cc_visibility_count_out(self, cr, uid):
    #     return self._assegnato_a_mio_ufficio_cc_visibility_count(cr, uid, "out")

    @api.cr_uid
    def _assegnato_a_mio_ufficio_cc_visibility_count_total(self, cr, uid):
        return self._assegnato_a_mio_ufficio_cc_visibility_count(cr, uid, "")

    def _assegnato_a_mio_ufficio_cc_visibility_count(self, cr, uid, protocollo_type):
        # if not protocollo_type:
        #     return 0

        time_start = datetime.datetime.now()
        archivio_ids = self.pool.get('protocollo.archivio').search(cr, uid, [('is_current', '=', True)])
        current_archivio_id = archivio_ids[0]

        sql_query = """SELECT COUNT(DISTINCT(pa.protocollo_id)) 
            FROM protocollo_protocollo pp, protocollo_assegnazione pa, hr_department hd, hr_employee he, resource_resource rr
            WHERE pp.archivio_id = %d 
                AND pp.id = pa.protocollo_id 
                AND pa.assegnatario_department_id = hd.id
                AND hd.id=he.department_id
                AND he.resource_id = rr.id
                AND rr.user_id = %d
                AND pp.registration_date IS NOT NULL
                AND pa.tipologia_assegnatario = 'department' 
                AND pa.tipologia_assegnazione = 'conoscenza'
                AND pa.state = 'assegnato'
                AND pp.state IN ('registered', 'notified', 'waiting', 'sent', 'error')
        """ % (current_archivio_id, uid)

        cr.execute(sql_query)
        result = cr.fetchall()
        count_value = result[0][0]

        time_end = datetime.datetime.now()
        time_duration = time_end - time_start

        _logger.info("_assegnato_a_mio_ufficio_cc_visibility_count: %d - %.03f s" % (
            count_value,
            float(time_duration.microseconds) / 1000000
        ))

        return count_value

    def _da_assegnare_visibility(self, cr, uid, ids, name, arg, context=None):
        return {}

    def _da_assegnare_visibility_search(self, cr, uid, obj, name, args, domain=None, context=None):
        start = int(round(time.time() * 1000))
        cr.execute('''
            SELECT DISTINCT(pp.id) 
            FROM protocollo_protocollo AS pp
            INNER JOIN hr_employee AS he ON pp.registration_employee_id = he.id
            INNER JOIN resource_resource AS rr ON he.resource_id = rr.id AND rr.user_id = %s 
            LEFT JOIN protocollo_assegnazione AS pa ON pp.id=pa.protocollo_id AND pa.tipologia_assegnazione = 'competenza'
            WHERE pp.state IN ('registered', 'notified', 'waiting', 'sent', 'error') AND 
                  pa.protocollo_id IS NULL AND 
                  pp.is_imported = FALSE
        ''', (uid,))
        protocollo_visible_ids = [res[0] for res in cr.fetchall()]
        end = int(round(time.time() * 1000))
        _logger.info("_da_assegnare_visibility_search" + str(end - start))
        return [('id', 'in', protocollo_visible_ids)]

    def _da_assegnare_general_visibility(self, cr, uid, ids, name, arg, context=None):
        return {}

    def _da_assegnare_general_visibility_search(self, cr, uid, obj, name, args, domain=None, context=None):
        start = int(round(time.time() * 1000))
        cr.execute('''
            SELECT DISTINCT(pp.id) 
            FROM protocollo_protocollo AS pp
            LEFT JOIN protocollo_assegnazione AS pa ON pp.id=pa.protocollo_id AND pa.tipologia_assegnazione = 'competenza'
            WHERE pp.state IN ('registered', 'notified', 'waiting', 'sent', 'error') AND 
                  pa.protocollo_id IS NULL
        ''', (uid,))
        protocollo_visible_ids = [res[0] for res in cr.fetchall()]
        end = int(round(time.time() * 1000))
        _logger.info("_da_assegnare_general_visibility_search" + str(end - start))
        return [('id', 'in', protocollo_visible_ids)]

    # @api.cr_uid
    # def _da_assegnare_visibility_count_in(self, cr, uid):
    #     return self._da_assegnare_visibility_count(cr, uid, "in")
    #
    # @api.cr_uid
    # def _da_assegnare_visibility_count_out(self, cr, uid):
    #     return self._da_assegnare_visibility_count(cr, uid, "out")

    @api.cr_uid
    def _da_assegnare_visibility_count_total(self, cr, uid):
        return self._da_assegnare_visibility_count(cr, uid, "")

    def _da_assegnare_visibility_count(self, cr, uid, protocollo_type):
        # if not protocollo_type:
        #     return 0

        time_start = datetime.datetime.now()
        archivio_ids = self.pool.get('protocollo.archivio').search(cr, uid, [('is_current', '=', True)])
        current_archivio_id = archivio_ids[0]

        sql_query = """SELECT COUNT(DISTINCT(pp.id)) 
            FROM protocollo_protocollo AS pp
            INNER JOIN hr_employee AS he ON pp.registration_employee_id = he.id
            INNER JOIN resource_resource AS rr ON he.resource_id = rr.id AND rr.user_id = %s 
            LEFT JOIN protocollo_assegnazione AS pa ON pp.id=pa.protocollo_id AND pa.tipologia_assegnazione = 'competenza'
            WHERE pp.state IN ('registered', 'notified', 'waiting', 'sent', 'error') AND
                  pp.archivio_id = %d AND 
                  pa.protocollo_id IS NULL AND 
                  pp.is_imported = FALSE
            """ % (uid, current_archivio_id)

        cr.execute(sql_query)
        result = cr.fetchall()
        count_value = result[0][0]

        time_end = datetime.datetime.now()
        time_duration = time_end - time_start

        _logger.info("_da_assegnare_visibility_count: %d - %.03f s" % (
            count_value,
            float(time_duration.microseconds) / 1000000
        ))

        return count_value

    def _assegnato_da_me_in_attesa_visibility(self, cr, uid, ids, name, arg, context=None):
        return {}

    def _assegnato_da_me_in_attesa_visibility_search(self, cr, uid, obj, name, args, domain=None, context=None):
        start = int(round(time.time() * 1000))
        cr.execute('''
            SELECT DISTINCT(pa.protocollo_id) 
            FROM protocollo_protocollo pp, protocollo_assegnazione pa, hr_employee he, resource_resource rr
            WHERE pp.id = pa.protocollo_id AND 
                  pa.assegnatore_id = he.id AND
                  he.resource_id = rr.id AND
                  rr.user_id = %s AND
                  pp.registration_date IS NOT NULL AND
                  pa.tipologia_assegnazione = 'competenza' AND
                  pa.state = 'assegnato' AND
                  (pa.tipologia_assegnatario = 'department' OR (pa.tipologia_assegnatario = 'employee' AND pa.parent_id IS NULL)) AND
                  pp.state IN ('registered', 'notified', 'waiting', 'sent', 'error')
        ''', (uid,))
        protocollo_visible_ids = [res[0] for res in cr.fetchall()]
        end = int(round(time.time() * 1000))
        _logger.info("_assegnato_da_me_in_attesa_visibility_search" + str(end - start))
        return [('id', 'in', protocollo_visible_ids)]

    # @api.cr_uid
    # def _assegnato_da_me_in_attesa_visibility_count_in(self, cr, uid):
    #     return self._assegnato_da_me_in_attesa_visibility_count(cr, uid, "in")
    #
    # @api.cr_uid
    # def _assegnato_da_me_in_attesa_visibility_count_out(self, cr, uid):
    #     return self._assegnato_da_me_in_attesa_visibility_count(cr, uid, "out")

    @api.cr_uid
    def _assegnato_da_me_in_attesa_visibility_count_total(self, cr, uid):
        return self._assegnato_da_me_in_attesa_visibility_count(cr, uid, "")

    def _assegnato_da_me_in_attesa_visibility_count(self, cr, uid, protocollo_type):
        # if not protocollo_type:
        #     return 0

        time_start = datetime.datetime.now()
        archivio_ids = self.pool.get('protocollo.archivio').search(cr, uid, [('is_current', '=', True)])
        current_archivio_id = archivio_ids[0]

        sql_query = """SELECT COUNT(DISTINCT(pa.protocollo_id)) 
            FROM protocollo_protocollo pp, protocollo_assegnazione pa, hr_employee he, resource_resource rr
            WHERE pp.archivio_id = %d 
                AND pp.id = pa.protocollo_id  
                AND pa.assegnatore_id = he.id 
                AND he.resource_id = rr.id 
                AND rr.user_id = %d 
                AND pp.registration_date IS NOT NULL 
                AND pa.tipologia_assegnazione = 'competenza' 
                AND pa.state = 'assegnato' 
                AND (pa.tipologia_assegnatario = 'department'
                    OR (pa.tipologia_assegnatario = 'employee'
                           AND pa.parent_id IS NULL
                    )
                )
                AND pp.state IN ('registered', 'notified', 'waiting', 'sent', 'error')
            """ % (current_archivio_id, uid)

        cr.execute(sql_query)
        result = cr.fetchall()
        count_value = result[0][0]

        time_end = datetime.datetime.now()
        time_duration = time_end - time_start

        _logger.info("_assegnato_da_me_in_attesa_visibility_count: %d - %.03f s" % (
            count_value,
            float(time_duration.microseconds) / 1000000
        ))

        return count_value

    def _assegnato_da_me_in_rifiutato_visibility(self, cr, uid, ids, name, arg, context=None):
        return {}

    def _assegnato_da_me_in_rifiutato_visibility_search(self, cr, uid, obj, name, args, domain=None, context=None):
        start = int(round(time.time() * 1000))
        cr.execute('''
            SELECT DISTINCT(pa.protocollo_id) 
            FROM protocollo_protocollo pp, protocollo_assegnazione pa, hr_employee he, resource_resource rr
            WHERE pp.id = pa.protocollo_id AND 
                  pa.assegnatore_id = he.id AND
                  he.resource_id = rr.id AND
                  rr.user_id = %s AND
                  pp.registration_date IS NOT NULL AND
                  pa.tipologia_assegnazione = 'competenza' AND
                  pa.state = 'rifiutato' AND 
                  pp.state IN ('registered', 'notified', 'waiting', 'sent', 'error')
        ''', (uid,))
        protocollo_visible_ids = [res[0] for res in cr.fetchall()]
        end = int(round(time.time() * 1000))
        _logger.info("_assegnato_da_me_in_rifiutato_visibility_search" + str(end - start))
        return [('id', 'in', protocollo_visible_ids)]

    # @api.cr_uid
    # def _assegnato_da_me_in_rifiutato_visibility_count_in(self, cr, uid):
    #     return self._assegnato_da_me_in_rifiutato_visibility_count(cr, uid, "in")
    #
    # @api.cr_uid
    # def _assegnato_da_me_in_rifiutato_visibility_count_out(self, cr, uid):
    #     return self._assegnato_da_me_in_rifiutato_visibility_count(cr, uid, "out")

    @api.cr_uid
    def _assegnato_da_me_in_rifiutato_visibility_count_total(self, cr, uid):
        return self._assegnato_da_me_in_rifiutato_visibility_count(cr, uid, "")

    def _assegnato_da_me_in_rifiutato_visibility_count(self, cr, uid, protocollo_type):
        # if not protocollo_type:
        #     return 0

        time_start = datetime.datetime.now()
        archivio_ids = self.pool.get('protocollo.archivio').search(cr, uid, [('is_current', '=', True)])
        current_archivio_id = archivio_ids[0]

        sql_query = """SELECT COUNT(DISTINCT(pa.protocollo_id))
            FROM protocollo_protocollo pp, protocollo_assegnazione pa, hr_employee he, resource_resource rr
            WHERE pp.archivio_id = %d 
                AND pp.id = pa.protocollo_id 
                AND pa.assegnatore_id = he.id
                AND he.resource_id = rr.id
                AND rr.user_id = %d
                AND pp.registration_date IS NOT NULL
                AND pa.tipologia_assegnazione = 'competenza'
                AND pa.state = 'rifiutato'
                AND pp.state IN ('registered', 'notified', 'waiting', 'sent', 'error')
        """ % (current_archivio_id, uid)

        cr.execute(sql_query)
        result = cr.fetchall()
        count_value = result[0][0]

        time_end = datetime.datetime.now()
        time_duration = time_end - time_start

        _logger.info("_assegnato_da_me_in_rifiutato_visibility_count: %d - %.03f s" % (
            count_value,
            float(time_duration.microseconds) / 1000000
        ))

        return count_value

    def _da_inviare_visibility(self, cr, uid, ids, name, arg, context=None):
        return {}

    def _da_inviare_visibility_search(self, cr, uid, obj, name, args, domain=None, context=None):
        start = int(round(time.time() * 1000))
        cr.execute('''
            SELECT DISTINCT(pp.id) 
            FROM protocollo_protocollo pp, hr_employee he, resource_resource rr
            WHERE pp.registration_employee_id = he.id AND
                  he.resource_id = rr.id AND
                  rr.user_id = %s AND
                  pp.registration_date IS NOT NULL AND
                  pp.type = 'out' AND 
                  pp.state IN ('registered', 'error')
        ''', (uid,))
        protocollo_visible_ids = [res[0] for res in cr.fetchall()]
        end = int(round(time.time() * 1000))
        _logger.info("_da_inviare_visibility_search" + str(end - start))
        return [('id', 'in', protocollo_visible_ids)]

    @api.cr_uid
    def _da_inviare_visibility_count_total(self, cr, uid):
        return self._da_inviare_visibility_count(cr, uid, "")

    def _da_inviare_visibility_count(self, cr, uid, protocollo_type):
        time_start = datetime.datetime.now()
        archivio_ids = self.pool.get('protocollo.archivio').search(cr, uid, [('is_current', '=', True)])
        current_archivio_id = archivio_ids[0]

        sql_query = """SELECT COUNT(DISTINCT(pp.id)) 
            FROM protocollo_protocollo pp, hr_employee he, resource_resource rr
            WHERE pp.archivio_id = %d AND
                  pp.registration_employee_id = he.id AND
                  he.resource_id = rr.id AND
                  rr.user_id = %s AND
                  pp.registration_date IS NOT NULL AND
                  pp.type = 'out' AND 
                  pp.state IN ('registered', 'error')
        """ % (current_archivio_id, uid)

        cr.execute(sql_query)
        result = cr.fetchall()
        count_value = result[0][0]

        time_end = datetime.datetime.now()
        time_duration = time_end - time_start

        _logger.info("_da_mettere_agli_atti_visibility_count: %d - %.03f s" % (
            count_value,
            float(time_duration.microseconds) / 1000000
        ))

        return count_value

    def _da_mettere_agli_atti_visibility(self, cr, uid, ids, name, arg, context=None):
        return {}

    def _da_mettere_agli_atti_visibility_search(self, cr, uid, obj, name, args, domain=None, context=None):
        start = int(round(time.time() * 1000))
        cr.execute('''
            SELECT DISTINCT(pa.protocollo_id) 
            FROM protocollo_protocollo pp, protocollo_assegnazione pa, hr_employee he, resource_resource rr
            WHERE pp.id = pa.protocollo_id AND 
                  pa.assegnatario_employee_id = he.id AND
                  he.resource_id = rr.id AND
                  rr.user_id = %s AND
                  pp.registration_date IS NOT NULL AND
                  pa.tipologia_assegnatario = 'employee' AND 
                  pa.tipologia_assegnazione = 'competenza' AND
                  pa.state = 'preso' AND
                  pp.state IN ('registered', 'notified', 'waiting', 'sent', 'error')
        ''', (uid,))
        protocollo_visible_ids = [res[0] for res in cr.fetchall()]
        end = int(round(time.time() * 1000))
        _logger.info("_da_mettere_agli_atti_visibility_search" + str(end - start))
        return [('id', 'in', protocollo_visible_ids)]

    def _da_mettere_agli_atti_general_visibility(self, cr, uid, ids, name, arg, context=None):
        return {}

    def _da_mettere_agli_atti_general_visibility_search(self, cr, uid, obj, name, args, domain=None, context=None):
        start = int(round(time.time() * 1000))
        cr.execute('''
            SELECT DISTINCT(pa.protocollo_id) 
            FROM protocollo_protocollo pp, protocollo_assegnazione pa
            WHERE pp.id = pa.protocollo_id AND 
                  pp.registration_date IS NOT NULL AND
                  pp.state IN ('registered', 'notified', 'waiting', 'sent', 'error')
        ''', (uid,))
        protocollo_visible_ids = [res[0] for res in cr.fetchall()]
        end = int(round(time.time() * 1000))
        _logger.info("_da_mettere_agli_atti_general_visibility_search" + str(end - start))
        return [('id', 'in', protocollo_visible_ids)]

    @api.cr_uid
    def _da_mettere_agli_atti_visibility_count_total(self, cr, uid):
        return self._da_mettere_agli_atti_visibility_count(cr, uid, "")

    def _da_mettere_agli_atti_visibility_count(self, cr, uid, protocollo_type):
        time_start = datetime.datetime.now()
        archivio_ids = self.pool.get('protocollo.archivio').search(cr, uid, [('is_current', '=', True)])
        current_archivio_id = archivio_ids[0]

        sql_query = """SELECT COUNT(DISTINCT(pa.protocollo_id)) 
            FROM protocollo_protocollo pp, protocollo_assegnazione pa, hr_employee he, resource_resource rr
            WHERE pp.archivio_id = %d AND
                  pp.id = pa.protocollo_id AND 
                  pa.assegnatario_employee_id = he.id AND
                  he.resource_id = rr.id AND
                  rr.user_id = %s AND
                  pp.registration_date IS NOT NULL AND
                  pa.tipologia_assegnatario = 'employee' AND 
                  pa.tipologia_assegnazione = 'competenza' AND
                  pa.state = 'preso' AND
                  pp.state IN ('registered', 'notified', 'waiting', 'sent', 'error')
        """ % (current_archivio_id, uid)

        cr.execute(sql_query)
        result = cr.fetchall()
        count_value = result[0][0]

        time_end = datetime.datetime.now()
        time_duration = time_end - time_start

        _logger.info("_da_mettere_agli_atti_visibility_count: %d - %.03f s" % (
            count_value,
            float(time_duration.microseconds) / 1000000
        ))

        return count_value

    ####################################################################################################################
    # Filtri sulle viste tree dei protocolli
    ####################################################################################################################

    def _get_protocollo_assegnazione_ids(self, cr, uid, tipologia_assegnazione, tipologia_assegnatario, nome):
        cr.execute('''
            SELECT DISTINCT(pa.protocollo_id) 
            FROM protocollo_protocollo pp, protocollo_assegnazione pa, protocollo_assegnatario ass
            WHERE pp.id = pa.protocollo_id AND 
                  pa.tipologia_assegnazione = %s AND
                  pa.tipologia_assegnatario = %s AND
                  pa.parent_id IS NULL AND
                  pa.assegnatario_id = ass.id AND 
                  ass.nome ILIKE %s
        ''', (tipologia_assegnazione, tipologia_assegnatario, '%' + nome + '%',))
        protocollo_ids = [res[0] for res in cr.fetchall()]
        return protocollo_ids

    def _get_assegnazione_competenza_dipendente_ids(self, cr, uid, ids, field_names, arg=None, context=None):
        result = dict((res_id, []) for res_id in ids)
        return result

    def _search_assegnazione_competenza_dipendente_ids(self, cr, uid, obj, name, args, domain=None, context=None):
        #TODO: gestire gli altri casi della ricerca
        return [('id', 'in', self._get_protocollo_assegnazione_ids(cr, uid, 'competenza', 'employee', args[0][2]))]

    def _get_assegnazione_competenza_ufficio_ids(self, cr, uid, ids, field_names, arg=None, context=None):
        result = dict((res_id, []) for res_id in ids)
        return result

    def _search_assegnazione_competenza_ufficio_ids(self, cr, uid, obj, name, args, domain=None, context=None):
        #TODO: gestire gli altri casi della ricerca
        return [('id', 'in', self._get_protocollo_assegnazione_ids(cr, uid, 'competenza', 'department', args[0][2]))]

    def _get_assegnazione_conoscenza_dipendente_ids(self, cr, uid, ids, field_names, arg=None, context=None):
        result = dict((res_id, []) for res_id in ids)
        return result

    def _search_assegnazione_conoscenza_dipendente_ids(self, cr, uid, obj, name, args, domain=None, context=None):
        #TODO: gestire gli altri casi della ricerca
        return [('id', 'in', self._get_protocollo_assegnazione_ids(cr, uid, 'conoscenza', 'employee', args[0][2]))]

    def _get_assegnazione_conoscenza_ufficio_ids(self, cr, uid, ids, field_names, arg=None, context=None):
        result = dict((res_id, []) for res_id in ids)
        return result

    def _search_assegnazione_conoscenza_ufficio_ids(self, cr, uid, obj, name, args, domain=None, context=None):
        #TODO: gestire gli altri casi della ricerca
        return [('id', 'in', self._get_protocollo_assegnazione_ids(cr, uid, 'conoscenza', 'department', args[0][2]))]

    def _filtro_a_me_competenza_visibility(self, cr, uid, ids, name, arg, context=None):
        return {}

    def _filtro_a_me_competenza_visibility_search(self, cr, uid, obj, name, args, domain=None, context=None):
        start = int(round(time.time() * 1000))

        cr.execute('''
            SELECT DISTINCT(pa.protocollo_id) 
            FROM protocollo_protocollo pp, protocollo_assegnazione pa, hr_employee he, resource_resource rr
            WHERE pp.id = pa.protocollo_id AND 
                  pa.assegnatario_employee_id = he.id AND
                  he.resource_id = rr.id AND
                  rr.user_id = %s AND
                  pp.registration_date IS NOT NULL AND
                  pa.tipologia_assegnatario = 'employee' AND 
                  pa.parent_id IS NULL AND
                  pa.tipologia_assegnazione = 'competenza'
        ''', (uid,))
        protocollo_visible_ids = [res[0] for res in cr.fetchall()]
        end = int(round(time.time() * 1000))
        _logger.info("_filtro_a_me_competenza_visibility_search: " + str(end - start))
        return [('id', 'in', protocollo_visible_ids)]

    def _filtro_a_me_conoscenza_visibility(self, cr, uid, ids, name, arg, context=None):
        return {}

    def _filtro_a_me_conoscenza_visibility_search(self, cr, uid, obj, name, args, domain=None, context=None):
        start = int(round(time.time() * 1000))

        cr.execute('''
            SELECT DISTINCT(pa.protocollo_id) 
            FROM protocollo_protocollo pp, protocollo_assegnazione pa, hr_employee he, resource_resource rr
            WHERE pp.id = pa.protocollo_id AND 
                  pa.assegnatario_employee_id = he.id AND
                  he.resource_id = rr.id AND
                  rr.user_id = %s AND
                  pp.registration_date IS NOT NULL AND
                  pa.tipologia_assegnatario = 'employee' AND 
                  pa.parent_id IS NULL AND
                  pa.tipologia_assegnazione = 'conoscenza'
        ''', (uid,))
        protocollo_visible_ids = [res[0] for res in cr.fetchall()]
        end = int(round(time.time() * 1000))
        _logger.info("_filtro_a_me_conocenza_visibility_search: " + str(end - start))
        return [('id', 'in', protocollo_visible_ids)]

    def _filtro_a_mio_ufficio_visibility(self, cr, uid, ids, name, arg, context=None):
        return {}

    def _filtro_a_mio_ufficio_visibility_search(self, cr, uid, obj, name, args, domain=None, context=None):
        start = int(round(time.time() * 1000))
        cr.execute('''
            SELECT DISTINCT(pa.protocollo_id) 
            FROM protocollo_protocollo pp, protocollo_assegnazione pa, hr_department hd, hr_employee he, resource_resource rr
            WHERE pp.id = pa.protocollo_id AND 
                  pa.assegnatario_department_id = hd.id AND
                  hd.id=he.department_id AND
                  he.resource_id = rr.id AND
                  rr.user_id = %s AND
                  pp.registration_date IS NOT NULL AND
                  pa.tipologia_assegnatario = 'department' AND 
                  pa.tipologia_assegnazione = 'competenza'
        ''', (uid,))
        protocollo_visible_ids = [res[0] for res in cr.fetchall()]
        end = int(round(time.time() * 1000))
        _logger.info("_filtro_a_mio_ufficio_visibility_search: " + str(end - start))
        return [('id', 'in', protocollo_visible_ids)]

    def _filtro_a_mio_ufficio_cc_visibility(self, cr, uid, ids, name, arg, context=None):
        return {}

    def _filtro_a_mio_ufficio_cc_visibility_search(self, cr, uid, obj, name, args, domain=None, context=None):
        start = int(round(time.time() * 1000))
        cr.execute('''
            SELECT DISTINCT(pa.protocollo_id) 
            FROM protocollo_protocollo pp, protocollo_assegnazione pa, hr_department hd, hr_employee he, resource_resource rr
            WHERE pp.id = pa.protocollo_id AND 
                  pa.assegnatario_department_id = hd.id AND
                  hd.id=he.department_id AND
                  he.resource_id = rr.id AND
                  rr.user_id = %s AND
                  pp.registration_date IS NOT NULL AND
                  pa.tipologia_assegnatario = 'department' AND 
                  pa.tipologia_assegnazione = 'conoscenza'
        ''', (uid,))
        protocollo_visible_ids = [res[0] for res in cr.fetchall()]
        end = int(round(time.time() * 1000))
        _logger.info("_filtro_a_mio_ufficio_cc_visibility_search" + str(end - start))
        return [('id', 'in', protocollo_visible_ids)]

    def _filtro_da_me_visibility(self, cr, uid, ids, name, arg, context=None):
        return {}

    def _filtro_da_me_visibility_search(self, cr, uid, obj, name, args, domain=None, context=None):
        start = int(round(time.time() * 1000))

        cr.execute('''
            SELECT DISTINCT(pa.protocollo_id) 
            FROM protocollo_protocollo pp, protocollo_assegnazione pa, hr_employee he, resource_resource rr
            WHERE pp.id = pa.protocollo_id AND 
                  pa.assegnatore_id = he.id AND
                  he.resource_id = rr.id AND
                  rr.user_id = %s AND
                  pp.registration_date IS NOT NULL AND
                  (pa.tipologia_assegnatario = 'department' OR (pa.tipologia_assegnatario = 'employee' AND pa.parent_id IS NULL)) 
        ''', (uid,))
        protocollo_visible_ids = [res[0] for res in cr.fetchall()]
        end = int(round(time.time() * 1000))
        _logger.info("_filtro_da_me_visibility_search: " + str(end - start))
        return [('id', 'in', protocollo_visible_ids)]

    def _filtro_competenza_visibility(self, cr, uid, ids, name, arg, context=None):
        return {}

    def _filtro_competenza_visibility_search(self, cr, uid, obj, name, args, domain=None, context=None):
        start = int(round(time.time() * 1000))
        cr.execute('''
            SELECT DISTINCT(pa.protocollo_id) 
            FROM protocollo_protocollo pp, protocollo_assegnazione pa, hr_employee he, resource_resource rr
            WHERE pp.id = pa.protocollo_id AND 
                  pa.assegnatore_id = he.id AND
                  he.resource_id = rr.id AND
                  pp.registration_date IS NOT NULL AND
                  pa.tipologia_assegnazione = 'competenza'
        ''', (uid,))
        protocollo_visible_ids = [res[0] for res in cr.fetchall()]
        end = int(round(time.time() * 1000))
        _logger.info("_filtro_competenza_visibility_search" + str(end - start))
        return [('id', 'in', protocollo_visible_ids)]

    def _filtro_conoscenza_visibility(self, cr, uid, ids, name, arg, context=None):
        return {}

    def _filtro_conoscenza_visibility_search(self, cr, uid, obj, name, args, domain=None, context=None):
        start = int(round(time.time() * 1000))
        cr.execute('''
            SELECT DISTINCT(pa.protocollo_id) 
            FROM protocollo_protocollo pp, protocollo_assegnazione pa, hr_employee he, resource_resource rr
            WHERE pp.id = pa.protocollo_id AND 
                  pa.assegnatore_id = he.id AND
                  he.resource_id = rr.id AND
                  pp.registration_date IS NOT NULL AND
                  pa.tipologia_assegnazione = 'conoscenza'
        ''', (uid,))
        protocollo_visible_ids = [res[0] for res in cr.fetchall()]
        end = int(round(time.time() * 1000))
        _logger.info("_filtro_conoscenza_visibility_search" + str(end - start))
        return [('id', 'in', protocollo_visible_ids)]

    # def _filtro_in_attesa_visibility(self, cr, uid, ids, name, arg, context=None):
    #     return {}
    #
    # def _filtro_in_attesa_visibility_search(self, cr, uid, obj, name, args, domain=None, context=None):
    #     start = int(round(time.time() * 1000))
    #     cr.execute('''
    #         SELECT DISTINCT(pa.protocollo_id)
    #         FROM protocollo_protocollo pp, protocollo_assegnazione pa
    #         WHERE pp.id = pa.protocollo_id AND
    #               pp.registration_employee_id IS NOT NULL AND
    #               pa.state = 'assegnato' AND
    #               pa.tipologia_assegnazione = 'competenza' AND
    #               pa.parent_id IS NULL
    #     ''', (uid,))
    #     protocollo_visible_ids = [res[0] for res in cr.fetchall()]
    #     end = int(round(time.time() * 1000))
    #     _logger.info("_filtro_in_attesa_visibility_search" + str(end - start))
    #     return [('id', 'in', protocollo_visible_ids)]
    #
    # def _filtro_rifiutato_visibility(self, cr, uid, ids, name, arg, context=None):
    #     return {}
    #
    # def _filtro_rifiutato_visibility_search(self, cr, uid, obj, name, args, domain=None, context=None):
    #     start = int(round(time.time() * 1000))
    #     cr.execute('''
    #         SELECT DISTINCT(pa.protocollo_id)
    #         FROM protocollo_protocollo pp, protocollo_assegnazione pa
    #         WHERE pp.id = pa.protocollo_id AND
    #               pp.registration_employee_id IS NOT NULL AND
    #               pa.state = 'rifiutato' AND
    #               pa.tipologia_assegnazione = 'competenza' AND
    #               pa.parent_id IS NULL
    #     ''', (uid,))
    #     protocollo_visible_ids = [res[0] for res in cr.fetchall()]
    #     end = int(round(time.time() * 1000))
    #     _logger.info("_filtro_rifiutato_visibility_search" + str(end - start))
    #     return [('id', 'in', protocollo_visible_ids)]
    #
    # def _filtro_preso_in_carico_visibility(self, cr, uid, ids, name, arg, context=None):
    #     return {}
    #
    # def _filtro_preso_in_carico_visibility_search(self, cr, uid, obj, name, args, domain=None, context=None):
    #     start = int(round(time.time() * 1000))
    #     cr.execute('''
    #                 SELECT DISTINCT(pa.protocollo_id)
    #                 FROM protocollo_protocollo pp, protocollo_assegnazione pa
    #                 WHERE pp.id = pa.protocollo_id AND
    #                       pp.registration_employee_id IS NOT NULL AND
    #                       pa.state = 'preso' AND
    #                       pa.tipologia_assegnazione = 'competenza' AND
    #                       pa.parent_id IS NULL
    #             ''', (uid,))
    #     protocollo_visible_ids = [res[0] for res in cr.fetchall()]
    #     end = int(round(time.time() * 1000))
    #     _logger.info("_filtro_preso_in_carico_visibility_search" + str(end - start))
    #     return [('id', 'in', protocollo_visible_ids)]

    ####################################################################################################################
    # Visibilità dei button sui protocolli
    ####################################################################################################################

    def _registra_visibility(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []

        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:
            check = False

            if protocollo.state == 'draft':
                check = True

            if check:
                types = self.get_protocollo_types_by_group(cr, uid, 'seedoo_protocollo', 'group_registra_protocollo_', '')
                check_gruppi = protocollo.type in types
                check = check and check_gruppi

            res.append((protocollo.id, check))

        return dict(res)

    def _annulla_visibility(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []

        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:
            check = False

            if protocollo.state in ['registered', 'notified', 'sent', 'waiting', 'error']:
                check = True

            if check:
                types = self.get_protocollo_types_by_group(cr, uid, 'seedoo_protocollo', 'group_annulla_protocollo_', '')
                check_gruppi = protocollo.type in types
                check = check and check_gruppi

            res.append((protocollo.id, check))

        return dict(res)

    def prendi_in_carico_validation(self, cr, uid, protocollo, context={}):
        if not (protocollo.state in ('registered', 'notified', 'waiting', 'sent', 'error')):
            return False, _("il protocollo non può essere preso in carico nello stato attuale")

        if not protocollo.assegnazione_competenza_ids:
            return False, _("il protocollo non ha nessuna assegnazione per competenza")

        if protocollo.assegnazione_competenza_ids[0].state != 'assegnato':
            return False, _("lo stato dell'assegnazione per competenza deve essere 'Assegnato'")

        assegnatario_employee_id = None
        if context and 'assegnatario_employee_id' in context and context['assegnatario_employee_id']:
            assegnatario_employee_id = context['assegnatario_employee_id']

        if protocollo.assegnazione_competenza_ids[0].tipologia_assegnatario == 'department':
            if not self._check_stato_assegnatario_competenza_ufficio(cr, uid, protocollo, 'assegnato', assegnatario_employee_id):
                return False, _("il dipendente non è un assegnatario per competenza del protocollo")
            if not assegnatario_employee_id:
                types = self.get_protocollo_types_by_group(cr, uid, 'seedoo_protocollo', 'group_prendi_in_carico_protocollo_', '')
                if not (protocollo.type in types):
                    type_str = ''
                    for selection_tuple_value in self._fields['type'].selection:
                        if protocollo.type == selection_tuple_value[0]:
                            type_str = selection_tuple_value[1]
                            break
                    return False, _("l'utente non possiede il permesso 'Presa in Carico Protocolli Assegnati Ufficio' per i protocolli di tipologia '%s'" % type_str)

        elif not self._check_stato_assegnatario_competenza(cr, uid, protocollo, 'assegnato', assegnatario_employee_id):
            return False, _("il dipendente non è un assegnatario per competenza del protocollo")

        return True, None

    def _prendi_in_carico_visibility(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []
        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:
            check, error = self.prendi_in_carico_validation(cr, uid, protocollo, context)
            res.append((protocollo.id, check))
        return dict(res)

    def rifiuta_validation(self, cr, uid, protocollo, context={}):
        if not (protocollo.state in ('registered', 'notified', 'waiting', 'sent', 'error')):
            return False, _("il protocollo non può essere preso in carico nello stato attuale")

        if not protocollo.assegnazione_competenza_ids:
            return False, _("il protocollo non ha nessuna assegnazione per competenza")

        if protocollo.assegnazione_competenza_ids[0].state != 'assegnato':
            return False, _("lo stato dell'assegnazione per competenza deve essere 'Assegnato'")

        assegnatario_employee_id = None
        if context and 'assegnatario_employee_id' in context and context['assegnatario_employee_id']:
            assegnatario_employee_id = context['assegnatario_employee_id']

        if protocollo.assegnazione_competenza_ids[0].tipologia_assegnatario == 'department':
            if not self._check_stato_assegnatario_competenza_ufficio(cr, uid, protocollo, 'assegnato', assegnatario_employee_id):
                return False, _("il dipendente non è un assegnatario per competenza del protocollo")
            if not assegnatario_employee_id:
                types = self.get_protocollo_types_by_group(cr, uid, 'seedoo_protocollo', 'group_rifiuta_protocollo_', '')
                if not (protocollo.type in types):
                    type_str = ''
                    for selection_tuple_value in self._fields['type'].selection:
                        if protocollo.type == selection_tuple_value[0]:
                            type_str = selection_tuple_value[1]
                            break
                    return False, _("l'utente non possiede il permesso 'Rifiuta Protocolli Assegnati Ufficio' per i protocolli di tipologia '%s'" % type_str)
        elif not self._check_stato_assegnatario_competenza(cr, uid, protocollo, 'assegnato', assegnatario_employee_id):
            return False, _("il dipendente non è un assegnatario per competenza del protocollo")

        return True, None

    def _rifiuta_visibility(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []
        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:
            check, error = self.rifiuta_validation(cr, uid, protocollo, context)
            res.append((protocollo.id, check))
        return dict(res)

    def _segna_come_letto_visibility(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []

        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:
            check = False


            #TODO: modificare controllando per singolo ufficio
            if protocollo.state in ('registered', 'notified', 'waiting', 'sent', 'error', 'acts') and \
                     protocollo.assegnazione_conoscenza_ids:
                check = True

            if check:
                check = self._check_stato_assegnatario_conoscenza(cr, uid, protocollo, 'assegnato')
                types = self.get_protocollo_types_by_group(cr, uid, 'seedoo_protocollo', 'group_segna_come_letto_protocollo_', '')
                check_gruppi = protocollo.type in types
                check = check and check_gruppi
            else:
                check = False

            res.append((protocollo.id, check))

        return dict(res)

    def _agli_atti_visibility(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []

        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:
            check = False

            if protocollo.state in ('registered', 'waiting', 'error', 'sent'):
                check = True

            if check:
                types = self.get_protocollo_types_by_group(cr, uid, 'seedoo_protocollo', 'group_agli_atti_protocollo_', '')
                check_gruppi = protocollo.type in types
                check = check and check_gruppi

            if self._check_stato_assegnatario_competenza(cr, uid, protocollo, 'preso') or uid == SUPERUSER_ID:
                check = check and True
            else:
                check = False

            res.append((protocollo.id, check))

        return dict(res)

    def _modifica_dati_generali_visibility(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []

        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:
            check = False

            if protocollo.state in ('registered', 'notified', 'error'):
                check = True

            if check:
                types = self.get_protocollo_types_by_group(cr, uid, 'seedoo_protocollo', 'group_modifica_protocollo_', '')
                check_gruppi = protocollo.type in types
                check = check and check_gruppi

            if uid == protocollo.user_id.id or uid == SUPERUSER_ID:
                check = check and True
            else:
                check = False
            # else:
            #     check_assegnatari = False
            # if check:
            #     check_assegnatari = self._check_stato_assegnatario_competenza(cr, uid, protocollo, 'preso')
            # check = check and check_assegnatari

            res.append((protocollo.id, check))

        return dict(res)

    def _aggiungi_mittenti_visibility(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []

        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:
            check = False

            if protocollo.type=='in' and protocollo.state in ['draft'] and not protocollo.senders:
                check = True

            res.append((protocollo.id, check))

        return dict(res)

    def _modifica_mittenti_visibility(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []

        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:
            check = False

            if protocollo.type=='in' and protocollo.state in ['draft']:
                check = True

            res.append((protocollo.id, check))

        return dict(res)

    def _aggiungi_destinatari_visibility(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []

        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:
            check = False

            if protocollo.type=='out' and protocollo.state in ['draft']:
                check = True

            res.append((protocollo.id, check))

        return dict(res)

    def _modifica_destinatari_visibility(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []

        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:
            check = False

            if protocollo.type=='out' and protocollo.state in ['draft']:
                check = True

            res.append((protocollo.id, check))

        return dict(res)

    def _aggiungi_mittente_interno_visibility(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []

        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:
            check = False

            if protocollo.type!='in' and protocollo.state in ['draft'] and not protocollo.sender_internal_name:
                check = True

            res.append((protocollo.id, check))

        return dict(res)

    def _modifica_mittente_interno_visibility(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []

        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:
            check = False

            if protocollo.type!='in' and protocollo.state in ['draft'] and protocollo.sender_internal_name:
                check = True

            res.append((protocollo.id, check))

        return dict(res)

    def _aggiungi_classificazione_visibility(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []

        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:
            check = False

            if protocollo.state in ['draft'] and not protocollo.classification:
                check = True

            res.append((protocollo.id, check))

        return dict(res)

    #TODO: attualmente rendiamo il button visibile solo al protocollatore, in futuro dovrà essere estesa anche all'assegnatore
    def _modifica_classificazione_visibility(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []

        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:
            check = False

            if protocollo.classification and (uid == protocollo.user_id.id or uid == SUPERUSER_ID):
                if protocollo.state == 'draft':
                    check = True
                elif protocollo.state in ['registered', 'notified', 'waiting', 'sent', 'error']:
                    types = self.get_protocollo_types_by_group(cr, uid, 'seedoo_protocollo', 'group_modifica_classificazione_protocollo_', '')
                    check = protocollo.type in types

            res.append((protocollo.id, check))

        return dict(res)

    def _classifica_visibility(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []

        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:
            check = False

            if protocollo.state in (
                    'registered', 'notified', 'waiting', 'sent', 'error') and not protocollo.classification:
                check = True

            if check:
                types = self.get_protocollo_types_by_group(cr, uid, 'seedoo_protocollo', 'group_classifica_protocollo_', '')
                check_gruppi = protocollo.type in types
                check = check and check_gruppi

            if uid == protocollo.user_id.id or uid == SUPERUSER_ID:
                check = check and True
            else:
                check_assegnatari = False
                if check:
                    check_assegnatari = self._check_stato_assegnatario_competenza(cr, uid, protocollo, 'preso')
                check = check and check_assegnatari

            res.append((protocollo.id, check))

        return dict(res)

    def _aggiungi_fascicolazione_visibility(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []

        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:
            check = False

            if not protocollo.dossier_ids:
                if protocollo.state == 'draft' and (uid == protocollo.user_id.id or uid == SUPERUSER_ID):
                    check = True
                elif protocollo.state in ['registered', 'notified', 'waiting', 'sent', 'error']:
                    types = self.get_protocollo_types_by_group(cr, uid, 'seedoo_protocollo', 'group_modifica_fascicolazione_protocollo_', '')
                    check = protocollo.type in types

            res.append((protocollo.id, check))

        return dict(res)

    def _modifica_fascicolazione_visibility(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []

        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:
            check = False

            if protocollo.dossier_ids:
                if protocollo.state == 'draft' and (uid == protocollo.user_id.id or uid == SUPERUSER_ID):
                    check = True
                elif protocollo.state in ['registered', 'notified', 'waiting', 'sent', 'error']:
                    types = self.get_protocollo_types_by_group(cr, uid, 'seedoo_protocollo', 'group_modifica_fascicolazione_protocollo_', '')
                    check = protocollo.type in types

            res.append((protocollo.id, check))

        return dict(res)

    def _fascicola_visibility(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []

        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:
            check = False

            if protocollo.state in ('registered', 'notified', 'waiting', 'sent', 'error') and not protocollo.dossier_ids:
                check = True

            if check:
                types = self.get_protocollo_types_by_group(cr, uid, 'seedoo_protocollo', 'group_fascicola_protocollo_', '')
                check_gruppi = protocollo.type in types
                check = check and check_gruppi

            if uid == protocollo.user_id.id or uid == SUPERUSER_ID:
                check = check and True
            else:
                check_assegnatari = False
                if check:
                    check_assegnatari = self._check_stato_assegnatario_competenza(cr, uid, protocollo, 'preso')
                check = check and check_assegnatari

            res.append((protocollo.id, check))

        return dict(res)

    def _aggiungi_assegnatari_visibility(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []

        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:
            check = False

            if protocollo.state == 'draft' and not protocollo.assegnazione_first_level_ids:
                check = True

            res.append((protocollo.id, check))

        return dict(res)

    def _modifica_assegnatari_visibility(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []

        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:
            check = False

            if protocollo.assegnazione_first_level_ids:

                if protocollo.state == 'draft' and (uid == protocollo.user_id.id or uid == SUPERUSER_ID):
                    check = True
                elif protocollo.state in ['registered', 'notified', 'waiting', 'sent', 'error']:
                    types = self.get_protocollo_types_by_group(cr, uid, 'seedoo_protocollo', 'group_modifica_assegnatari_protocollo_', '')
                    check = protocollo.type in types

            res.append((protocollo.id, check))

        return dict(res)

    def _aggiungi_assegnatari_cc_visibility(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []

        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:
            check = False

            if protocollo.state in ('registered', 'notified', 'waiting', 'sent', 'error') \
                    and protocollo.assegnazione_competenza_ids and not protocollo.reserved:
                check = True

            if check:
                types = self.get_protocollo_types_by_group(cr, uid, 'seedoo_protocollo', 'group_aggiungi_assegnatari_cc_protocollo_', '')
                check_gruppi = protocollo.type in types
                check = check and check_gruppi

            if uid == protocollo.user_id.id or uid == SUPERUSER_ID:
                check = check and True
            else:
                check_assegnatari = False
                if check:
                    check_assegnatari = self._check_stato_assegnatario_competenza(cr, uid, protocollo, 'preso')
                check = check and check_assegnatari

            res.append((protocollo.id, check))

        return dict(res)

    def _assegna_visibility(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []

        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:
            check = False

            if protocollo.state in (
                    'registered', 'notified', 'waiting', 'sent',
                    'error') and not protocollo.assegnazione_competenza_ids:
                check = True

            if check:
                types = self.get_protocollo_types_by_group(cr, uid, 'seedoo_protocollo', 'group_assegna_protocollo_', '')
                check_gruppi = protocollo.type in types
                check = check and check_gruppi

            if uid == protocollo.user_id.id or uid == SUPERUSER_ID:
                check = check and True
            else:
                check = False

            res.append((protocollo.id, check))

        return dict(res)

    def _riassegna_visibility(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []

        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:
            check = False

            if protocollo.state in ('registered', 'notified', 'waiting', 'sent', 'error'):
                check = True

            if check:
                types = self.get_protocollo_types_by_group(cr, uid, 'seedoo_protocollo', 'group_riassegna_protocollo_', '')
                check_gruppi = protocollo.type in types
                check = check and check_gruppi

            if self._check_stato_assegnatore_competenza(cr, uid, protocollo, 'rifiutato') or uid==SUPERUSER_ID:
                check = check and True
            else:
                check = False

            res.append((protocollo.id, check))

        return dict(res)

    def _invio_pec_visibility(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []

        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:
            check = False

            if protocollo.state == 'registered' and protocollo.type == 'out' and protocollo.pec is True:
                check = True

            if check:
                dipendente_id = False
                if context and 'dipendente_id' in context and context['dipendente_id']:
                    dipendente_id = context['dipendente_id']
                if ((uid == protocollo.user_id.id or uid == SUPERUSER_ID) and self.user_has_groups(cr, uid, 'seedoo_protocollo.group_invia_protocollo_pec_uscita')) or \
                        protocollo.registration_employee_id.id == dipendente_id:
                    check = True
                else:
                    check = False

            res.append((protocollo.id, check))

        return dict(res)

    def _invio_sharedmail_visibility(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []

        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:
            check = False

            if protocollo.state == 'registered' and protocollo.type == 'out' and protocollo.sharedmail is True:
                check = True

            if check:
                dipendente_id = False
                if context and 'dipendente_id' in context and context['dipendente_id']:
                    dipendente_id = context['dipendente_id']
                if ((uid == protocollo.user_id.id or uid == SUPERUSER_ID) and self.user_has_groups(cr, uid, 'seedoo_protocollo.group_invia_protocollo_sharedmail_uscita')) or \
                        protocollo.registration_employee_id.id == dipendente_id:
                    check = True
                else:
                    check = False

            res.append((protocollo.id, check))

        return dict(res)

    def _invio_protocollo_visibility(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []

        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:
            check = False
            if protocollo.state == 'registered' and protocollo.type == 'out' and protocollo.pec is False and protocollo.sharedmail is False:
                check = True

            if check:
                dipendente_id = False
                if context and 'dipendente_id' in context and context['dipendente_id']:
                    dipendente_id = context['dipendente_id']
                if ((uid == protocollo.user_id.id or uid == SUPERUSER_ID) and self.user_has_groups(cr, uid, 'seedoo_protocollo.group_invia_protocollo_uscita')) or \
                        protocollo.registration_employee_id.id == dipendente_id:
                    check = True
                else:
                    check = False

            res.append((protocollo.id, check))

        return dict(res)

    def _modifica_pec_visibility(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []

        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:
            check = False
            if protocollo.type == 'out' and protocollo.pec is True and protocollo.state in ['waiting', 'sent', 'error']:
                if protocollo.sender_receivers:
                    for sender_receiver_id in protocollo.sender_receivers.ids:
                        sender_receiver_obj = self.pool.get('protocollo.sender_receiver').browse(cr, uid,
                                                                                                 sender_receiver_id,
                                                                                                 context=context)
                        if sender_receiver_obj.pec_errore_consegna_status or sender_receiver_obj.pec_non_accettazione_status:
                            check = True

            if check:
                if (uid == protocollo.user_id.id or uid == SUPERUSER_ID) and \
                        self.user_has_groups(cr, uid, 'seedoo_protocollo.group_modifica_destinatari_pec_uscita'):
                    check = True
                else:
                    check = False

            res.append((protocollo.id, check))

        return dict(res)

    def _modifica_email_visibility(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []

        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:
            check = False

            if protocollo.type == 'out' and protocollo.sharedmail == True and protocollo.state in ['sent', 'waiting', 'error', 'acts']:
                check = True

            if check:
                if (uid == protocollo.user_id.id or uid == SUPERUSER_ID) and \
                        self.user_has_groups(cr, uid, 'seedoo_protocollo.group_modifica_destinatari_email_uscita'):
                    check = True
                else:
                    check = False

            res.append((protocollo.id, check))

        return dict(res)

    def _aggiungi_pec_visibility(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []

        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:
            check = False
            if protocollo.type == 'out' and protocollo.pec is True and protocollo.state in ['waiting', 'sent', 'error']:
                check = True

            if check:
                if (uid == protocollo.user_id.id or uid == SUPERUSER_ID) and \
                        self.user_has_groups(cr, uid, 'seedoo_protocollo.group_aggiungi_destinatari_pec_uscita'):
                    check = True
                else:
                    check = False

            res.append((protocollo.id, check))

        return dict(res)

    def _protocollazione_riservata_visibility(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []

        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:
            check = self.user_has_groups(cr, uid, 'seedoo_protocollo.group_protocollazione_riservata')

            res.append((protocollo.id, check))

        return dict(res)

    def _inserisci_testo_mailpec_visibility(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []
        check = False
        configurazione_ids = self.pool.get('protocollo.configurazione').search(cr, uid, [])
        configurazione = self.pool.get('protocollo.configurazione').browse(cr, uid, configurazione_ids[0])
        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:

            if configurazione.inserisci_testo_mailpec:
                check = True

            res.append((protocollo.id, check))

        return dict(res)

    #TODO: aggiungere condizioni per stabilire la visualizzazione del button
    def _carica_allegati_visibility(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []
        check = False
        configurazione_ids = self.pool.get('protocollo.configurazione').search(cr, uid, [])
        configurazione = self.pool.get('protocollo.configurazione').browse(cr, uid, configurazione_ids[0])
        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:

            if protocollo.state == 'draft' or \
                    (protocollo.state == 'registered' and configurazione.aggiungi_allegati_post_registrazione):
                check = True

            res.append((protocollo.id, check))

        return dict(res)

    def _carica_documento_visibility(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []
        check = False
        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:

            if not protocollo.doc_id and \
                    (protocollo.state in 'draft' or (protocollo.state in 'registered' and protocollo.user_id.id == uid)):
                check = True

            res.append((protocollo.id, check))

        return dict(res)

    def _modifica_documento_visibility(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []
        check = False
        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:

            if protocollo.doc_id and protocollo.state in ['draft']:
                check = True

            res.append((protocollo.id, check))

        return dict(res)

    ####################################################################################################################
    # Modificabilità dei campi
    ####################################################################################################################
    def _protocollo_fields_editability(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []
        check = False
        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:
            if protocollo.state == 'draft':
                check = True
            res.append((protocollo.id, check))

        return dict(res)

    def _typology_editability(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []
        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:
            check = False
            if protocollo.protocollo_fields_editability and not protocollo.mail_pec_ref:
                check = True
            res.append((protocollo.id, check))
        return dict(res)
    ####################################################################################################################

    ####################################################################################################################
    # Obbligatorietà dei campi
    ####################################################################################################################
    def _server_sharedmail_id_required(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []
        check = False
        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:
            if protocollo.sharedmail and protocollo.type=='out':
                check = True
            res.append((protocollo.id, check))
        return dict(res)

    def _server_pec_id_required(self, cr, uid, ids, prop, unknow_none, context=None):
        res = []
        check = False
        protocolli = self._get_protocolli(cr, uid, ids)
        for protocollo in protocolli:
            if protocollo.pec and protocollo.type=='out':
                check = True
            res.append((protocollo.id, check))
        return dict(res)
    ####################################################################################################################

    _columns = {
        # Visibilità dei protocolli
        'is_visible': fields.function(_is_visible, fnct_search=_is_visible_search, type='boolean', string='Visibile'),

        # Visibilità dei protocolli nella dashboard
        'non_classificati_visibility': fields.function(_non_classificati_visibility,
                                                         fnct_search=_non_classificati_visibility_search,
                                                         type='boolean', string='Non Classificati'),
        'non_fascicolati_visibility': fields.function(_non_fascicolati_visibility,
                                                         fnct_search=_non_fascicolati_visibility_search,
                                                         type='boolean', string='Non Fascicolati'),
        'bozza_creato_da_me_visibility': fields.function(_bozza_creato_da_me_visibility,
                                                         fnct_search=_bozza_creato_da_me_visibility_search,
                                                         type='boolean', string='Bozza Creata da me'),
        'assegnato_a_me_visibility': fields.function(_assegnato_a_me_visibility,
                                                     fnct_search=_assegnato_a_me_visibility_search, type='boolean',
                                                     string='Assegnato a me per Competenza'),
        'assegnato_cc_visibility': fields.function(_assegnato_cc_visibility,
                                                   fnct_search=_assegnato_cc_visibility_search, type='boolean',
                                                   string='Assegnato per CC'),
        'assegnato_a_me_cc_visibility': fields.function(_assegnato_a_me_cc_visibility,
                                                        fnct_search=_assegnato_a_me_cc_visibility_search,
                                                        type='boolean', string='Assegnato a me per CC'),
        'assegnato_a_mio_ufficio_visibility': fields.function(_assegnato_a_mio_ufficio_visibility,
                                                              fnct_search=_assegnato_a_mio_ufficio_visibility_search,
                                                              type='boolean', string='Assegnato a me per CC'),
        'assegnato_a_mio_ufficio_cc_visibility': fields.function(_assegnato_a_mio_ufficio_cc_visibility,
                                                                 fnct_search=_assegnato_a_mio_ufficio_cc_visibility_search,
                                                                 type='boolean', string='Assegnato al mio Ufficio per Conoscenza'),
        'da_assegnare_visibility': fields.function(_da_assegnare_visibility,
                                                                fnct_search=_da_assegnare_visibility_search,
                                                                type='boolean', string='Da Assegnare'),
        'da_assegnare_general_visibility': fields.function(_da_assegnare_general_visibility,
                                                                fnct_search=_da_assegnare_general_visibility_search,
                                                                type='boolean', string='Da Assegnare'),
        'assegnato_da_me_in_attesa_visibility': fields.function(_assegnato_da_me_in_attesa_visibility,
                                                                fnct_search=_assegnato_da_me_in_attesa_visibility_search,
                                                                type='boolean', string='In Attesa'),
        'assegnato_da_me_in_rifiutato_visibility': fields.function(_assegnato_da_me_in_rifiutato_visibility,
                                                                   fnct_search=_assegnato_da_me_in_rifiutato_visibility_search,
                                                                   type='boolean', string='Rifiutato'),
        'da_inviare_visibility': fields.function(_da_inviare_visibility,
                                                                fnct_search=_da_inviare_visibility_search,
                                                                type='boolean', string='Da Inviare'),
        'da_mettere_agli_atti_visibility': fields.function(_da_mettere_agli_atti_visibility,
                                                                fnct_search=_da_mettere_agli_atti_visibility_search,
                                                                type='boolean', string='Da Mettere Agli Atti'),
        'da_mettere_agli_atti_general_visibility': fields.function(_da_mettere_agli_atti_general_visibility,
                                                                fnct_search=_da_mettere_agli_atti_general_visibility_search,
                                                                type='boolean', string='Da Mettere Agli Atti'),

        'filtro_assegnazione_competenza_dipendente_ids': fields.function(_get_assegnazione_competenza_dipendente_ids,
                                                          fnct_search=_search_assegnazione_competenza_dipendente_ids,
                                                          method=True,
                                                          type='one2many',
                                                          relation='protocollo.assegnazione',
                                                          string='Assegnatario Dipendente Competenza'),
        'filtro_assegnazione_competenza_ufficio_ids': fields.function(_get_assegnazione_competenza_ufficio_ids,
                                                         fnct_search=_search_assegnazione_competenza_ufficio_ids,
                                                         method=True,
                                                         type='one2many',
                                                         relation='protocollo.assegnazione',
                                                         string='Assegnatario Ufficio Competenza'),
        'filtro_assegnazione_conoscenza_dipendente_ids': fields.function(_get_assegnazione_conoscenza_dipendente_ids,
                                                         fnct_search=_search_assegnazione_conoscenza_dipendente_ids,
                                                         method=True,
                                                         type='one2many',
                                                         relation='protocollo.assegnazione',
                                                         string='Assegnatario Dipendente Conoscenza'),
        'filtro_assegnazione_conoscenza_ufficio_ids': fields.function(_get_assegnazione_conoscenza_ufficio_ids,
                                                          fnct_search=_search_assegnazione_conoscenza_ufficio_ids,
                                                          method=True,
                                                          type='one2many',
                                                          relation='protocollo.assegnazione',
                                                          string='Assegnatario Ufficio Conoscenza'),

        'filtro_a_me_competenza_visibility': fields.function(_filtro_a_me_competenza_visibility,
                                                             fnct_search=_filtro_a_me_competenza_visibility_search,
                                                             type='boolean', string='Assegnato a me per Competenza'),
        'filtro_a_me_conoscenza_visibility': fields.function(_filtro_a_me_conoscenza_visibility,
                                                             fnct_search=_filtro_a_me_conoscenza_visibility_search,
                                                             type='boolean', string='Assegnato a me per CC'),
        'filtro_a_mio_ufficio_visibility': fields.function(_filtro_a_mio_ufficio_visibility,
                                                           fnct_search=_filtro_a_mio_ufficio_visibility_search,
                                                           type='boolean', string='Assegnato al mio Ufficio per CC'),
        'filtro_a_mio_ufficio_cc_visibility': fields.function(_filtro_a_mio_ufficio_cc_visibility,
                                                              fnct_search=_filtro_a_mio_ufficio_cc_visibility_search,
                                                              type='boolean', string='Assegnato al mio Ufficio per Conoscenza'),
        'filtro_da_me_visibility': fields.function(_filtro_da_me_visibility,
                                                   fnct_search=_filtro_da_me_visibility_search, type='boolean',
                                                   string='Assegnato da me'),
        'filtro_competenza_visibility': fields.function(_filtro_competenza_visibility,
                                                        fnct_search=_filtro_competenza_visibility_search,
                                                        type='boolean', string='Assegnato da me per Competenza'),
        'filtro_conoscenza_visibility': fields.function(_filtro_conoscenza_visibility,
                                                        fnct_search=_filtro_conoscenza_visibility_search,
                                                        type='boolean', string='Assegnato da me per Conoscenza'),
        # 'filtro_in_attesa_visibility': fields.function(_filtro_in_attesa_visibility,
        #                                                fnct_search=_filtro_in_attesa_visibility_search, type='boolean',
        #                                                string='Visibile'),
        # 'filtro_rifiutato_visibility': fields.function(_filtro_rifiutato_visibility,
        #                                                fnct_search=_filtro_rifiutato_visibility_search, type='boolean',
        #                                                string='Visibile'),
        # 'filtro_preso_in_carico_visibility': fields.function(_filtro_preso_in_carico_visibility,
        #                                                      fnct_search=_filtro_preso_in_carico_visibility_search,
        #                                                      type='boolean', string='Visibile'),

        # Visibilità dei button sui protocolli
        'registra_visibility': fields.function(_registra_visibility, type='boolean', string='Registra'),
        'annulla_visibility': fields.function(_annulla_visibility, type='boolean', string='Annulla'),
        'prendi_in_carico_visibility': fields.function(_prendi_in_carico_visibility, type='boolean',
                                                       string='Prendi in Carico'),
        'rifiuta_visibility': fields.function(_rifiuta_visibility, type='boolean', string='Rifiuta'),
        'segna_come_letto_visibility': fields.function(_segna_come_letto_visibility, type='boolean', string='Segna come letto'),
        'agli_atti_visibility': fields.function(_agli_atti_visibility, type='boolean', string='Agli Atti'),
        'modifica_dati_generali_visibility': fields.function(_modifica_dati_generali_visibility, type='boolean',
                                                             string='Modifica Dati Generali'),
        'aggiungi_mittenti_visibility': fields.function(_aggiungi_mittenti_visibility, type='boolean', string='Aggiungi Mittenti'),
        'modifica_mittenti_visibility': fields.function(_modifica_mittenti_visibility, type='boolean', string='Modifica Mittenti'),
        'aggiungi_destinatari_visibility': fields.function(_aggiungi_destinatari_visibility, type='boolean', string='Aggiungi Destinatari'),
        'modifica_destinatari_visibility': fields.function(_modifica_destinatari_visibility, type='boolean', string='Modifica Destinatari'),
        'aggiungi_mittente_interno_visibility': fields.function(_aggiungi_mittente_interno_visibility, type='boolean', string='Aggiungi Mittente Interno'),
        'modifica_mittente_interno_visibility': fields.function(_modifica_mittente_interno_visibility, type='boolean', string='Modifica Mittente Interno'),
        'aggiungi_classificazione_visibility': fields.function(_aggiungi_classificazione_visibility, type='boolean', string='Aggiungi Classificazione'),
        'modifica_classificazione_visibility': fields.function(_modifica_classificazione_visibility, type='boolean', string='Modifica Classificazione'),
        'classifica_visibility': fields.function(_classifica_visibility, type='boolean', string='Classifica'),
        'aggiungi_fascicolazione_visibility': fields.function(_aggiungi_fascicolazione_visibility, type='boolean', string='Aggiungi Fascicolazione'),
        'modifica_fascicolazione_visibility': fields.function(_modifica_fascicolazione_visibility, type='boolean', string='Modifica Fascicolazione'),
        'fascicola_visibility': fields.function(_fascicola_visibility, type='boolean', string='Fascicola'),
        'aggiungi_assegnatari_visibility': fields.function(_aggiungi_assegnatari_visibility, type='boolean', string='Aggiungi Assegnatari'),
        'modifica_assegnatari_visibility': fields.function(_modifica_assegnatari_visibility, type='boolean', string='Modifica Assegnatari'),
        'aggiungi_assegnatari_cc_visibility': fields.function(_aggiungi_assegnatari_cc_visibility, type='boolean',
                                                              string='Aggiungi Assegnatari Conoscenza'),
        'assegna_visibility': fields.function(_assegna_visibility, type='boolean', string='Assegna'),
        'riassegna_visibility': fields.function(_riassegna_visibility, type='boolean', string='Riassegna per Rifiuto'),
        'invio_pec_visibility': fields.function(_invio_pec_visibility, type='boolean', string='Invio PEC'),
        'invio_sharedmail_visibility': fields.function(_invio_sharedmail_visibility, type='boolean',
                                                       string='Invio E-mail'),
        'invio_protocollo_visibility': fields.function(_invio_protocollo_visibility, type='boolean',
                                                       string='Invio Protocollo'),
        'modifica_pec_visibility': fields.function(_modifica_pec_visibility, type='boolean', string='Modifica PEC'),
        # 'aggiungi_pec_visibility': fields.function(_aggiungi_pec_visibility, type='boolean', string='Aggiungi PEC'),
        'modifica_email_visibility': fields.function(_modifica_email_visibility, type='boolean',
                                                     string='Modifica e-mail'),
        'protocollazione_riservata_visibility': fields.function(_protocollazione_riservata_visibility, type='boolean',
                                                                string='Protocollazione Riservata'),
        'inserisci_testo_mailpec_visibility': fields.function(_inserisci_testo_mailpec_visibility, type='boolean',
                                                              string='Abilita testo PEC'),
        'carica_documento_visibility': fields.function(_carica_documento_visibility, type='boolean', string='Carica documento'),
        'modifica_documento_visibility': fields.function(_modifica_documento_visibility, type='boolean', string='Modifica documento'),
        'carica_allegati_visibility': fields.function(_carica_allegati_visibility, type='boolean', string='Carica Allegati'),
        'protocollo_fields_editability': fields.function(_protocollo_fields_editability, type='boolean', string='Modificabilità Campi Protocollo'),
        'typology_editability': fields.function(_typology_editability, type='boolean', string='Modificabilità Campi Mezzo di Trasmissione'),
    }

    def _default_protocollazione_riservata_visibility(self, cr, uid, context):
        return self.user_has_groups(cr, uid, 'seedoo_protocollo.group_protocollazione_riservata')

    _defaults = {
        'protocollazione_riservata_visibility': _default_protocollazione_riservata_visibility,
        'carica_documento_visibility': True,
        'modifica_documento_visibility': True
    }

    def init(self, cr):

        cr.execute('SELECT indexname FROM pg_indexes WHERE indexname = \'idx_protocollo_protocollo_registration_date\'')
        if not cr.fetchone():
            cr.execute("""
            CREATE INDEX idx_protocollo_protocollo_registration_date
            ON public.protocollo_protocollo
            USING btree
            (registration_date);
        """)
        cr.execute('SELECT indexname FROM pg_indexes WHERE indexname = \'idx_protocollo_protocollo_registration_employee_id\'')
        if not cr.fetchone():
            cr.execute("""
            CREATE INDEX idx_protocollo_protocollo_registration_employee_id
            ON public.protocollo_protocollo
            USING btree
            (registration_employee_id);
        """)

        cr.execute('SELECT indexname FROM pg_indexes WHERE indexname = \'idx_protocollo_protocollo_registration_employee_department_id\'')
        if not cr.fetchone():
            cr.execute("""
            CREATE INDEX idx_protocollo_protocollo_registration_employee_department_id
            ON public.protocollo_protocollo
            USING btree
            (registration_employee_department_id);
        """)

    def fields_get(self, cr, uid, fields=None, context=None):
        # lista dei campi da nascondere nella ricerca avanzata
        fields_to_hide = [
            'is_visible',
            'registration_employee_id',
            'doc_fname',
            'assegnazione_first_level_ids',
            'assegnazione_competenza_ids',
            'assegnazione_conoscenza_ids',
            'filtro_assegnazione_competenza_dipendente_ids',
            'filtro_assegnazione_competenza_ufficio_ids',
            'filtro_assegnazione_conoscenza_dipendente_ids',
            'filtro_assegnazione_conoscenza_ufficio_ids',
            'filtro_a_me_conoscenza_visibility',
            'filtro_a_me_competenza_visibility',
            'filtro_a_mio_ufficio_visibility',
            'filtro_a_mio_ufficio_cc_visibility',
            'filtro_da_me_visibility',
            'filtro_competenza_visibility',
            'filtro_conoscenza_visibility',
            'bozza_creato_da_me_visibility',
            'assegnato_a_me_visibility',
            'assegnato_cc_visibility',
            'assegnato_a_me_cc_visibility',
            'assegnato_a_mio_ufficio_visibility',
            'assegnato_a_mio_ufficio_cc_visibility',
            'assegnato_da_me_in_attesa_visibility',
            'assegnato_da_me_in_rifiutato_visibility',
        ]
        res = super(protocollo_protocollo, self).fields_get(cr, uid, fields, context)
        for field in fields_to_hide:
            res[field]['selectable'] = False
        return res